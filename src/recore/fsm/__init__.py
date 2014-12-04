# -*- coding: utf-8 -*-
# Copyright © 2014 SEE AUTHORS FILE
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from bson.objectid import ObjectId
import json
from datetime import datetime as dt
import recore.mongo
import recore.amqp
import recore.constants
import recore.contextfilter
import logging
import os.path
import threading
import pika.spec
import pika.exceptions
import pymongo.errors
import ssl

RELEASE_LOG_DIR = None


# These method loggers are for EXTREME debugging purposes only
detailed_debugging = False

if detailed_debugging:
    dd_level = logging.DEBUG
else:
    dd_level = logging.NOTSET

method_logger = logging.getLogger("methodlogger")
method_logger.setLevel(dd_level)
method_logger_file_handler = logging.FileHandler("/tmp/fsm-debug.log")
method_logger_file_handler.setLevel(dd_level)
method_logger.addHandler(method_logger_file_handler)

method_logger_names = logging.getLogger("methodloggernames")
method_logger_names.setLevel(dd_level)
method_logger_file_handler_names = logging.FileHandler("/tmp/fsm-debug-names.log")
method_logger_file_handler_names.setLevel(dd_level)
method_logger_names.addHandler(method_logger_file_handler_names)


def method_wrapper(f):
    def decorator(*args, **kwargs):
        o = logging.getLogger('methodlogger')
        n = logging.getLogger('methodloggernames')
        o.debug("Entered: %s(%s, %s)" % (
            str(f.func_name),
            str(args[1:]),
            str(kwargs)))
        n.debug(f.func_name)
        return f(*args, **kwargs)
    return decorator


class FSM(threading.Thread):
    """The re-core Finite State Machine to oversee the execution of
a playbooks's release steps."""

    def __init__(self, playbook_id, state_id, *args, **kwargs):
        """Not really overriding the threading init method. Just describing
        the parameters we expect to receive when initialized and
        setting up logging.

        `state_id` - MongoDB ObjectID of the document holding release steps
        """
        super(FSM, self).__init__(*args, **kwargs)
        self.app_logger = fsm_logger(playbook_id, state_id)
        # properties for later when we run() like the wind
        self.ch = None
        self.conn = None
        self.state_id = state_id
        self.playbook_id = playbook_id
        _pb_logger = 'recore.playbook.' + playbook_id
        self.filter = recore.contextfilter.get_logger_filter(_pb_logger)
        self._id = {'_id': ObjectId(self.state_id)}
        self.initialized = False
        self.state = {}
        self.dynamic = {}
        self.reply_queue = None
        self.failed = False

    @method_wrapper
    def run(self):  # pragma: no cover
        try:
            self._run()
        except pika.exceptions.ConnectionClosed:
            # Don't know why, but pika likes to raise this exception
            # when we intentionally close a connection...
            self.app_logger.debug("Closed AMQP connection")

        if self.failed:
            self.app_logger.error("Terminating this FSM thread - deployment failed")
        else:
            self.app_logger.info("Terminating this FSM thread - deployment successful")

        return True

    @method_wrapper
    def _run(self):
        self._setup()
        try:
            # Pop a step off the remaining steps queue
            # - Reflect in MongoDB
            self.dequeue_next_active_step()
            self.app_logger.debug("Dequeued next active step. Updated currently active step.")
        except IndexError:
            # The previous step was the last step
            self.app_logger.debug("Processed all remaining steps for job with id: %s" % self.state_id)
            self.app_logger.debug("Cleaning up after release")
            # Now that we're done, clean up that queue and record end time
            self._cleanup()
            return True

        self.filter.set_field("deploy_phase", "execution")
        # Parse the step into a message for the worker queue
        props = pika.spec.BasicProperties()
        props.correlation_id = self.state_id
        props.reply_to = self.reply_queue
        params = {}
        notify = {}
        self.app_logger.debug("Pre-processing next step: %s" % str(self.active_step))
        if type(self.active_step) == str or \
           type(self.active_step) == unicode:
            self.app_logger.debug("Next step is a string. Split it and route it")
            (worker_queue, sep, subcommand) = self.active_step.partition(':')
        else:
            # It's a dictionary
            self.app_logger.debug("Next step has parameters to parse: %s" % self.active_step)
            _step_key = self.active_step.keys()[0]
            (worker_queue, sep, subcommand) = _step_key.partition(':')
            params = self.active_step[_step_key]
            notify.update(self.active_step[_step_key].get('notify', {}))

        this_step_name = "{CMD}:{SUB}".format(CMD=worker_queue, SUB=subcommand)
        self.filter.set_field("active_step", this_step_name)

        _params = {
            'command': worker_queue,
            'subcommand': subcommand,
            'hosts': self.active_sequence['hosts']
        }

        params.update(_params)
        msg = {
            'group': self.group,
            'parameters': params,
            'dynamic': self.dynamic,
            'notify': notify
        }
        plugin_queue = "worker.%s" % worker_queue

        # Send message to the worker with instructions and dynamic data
        _exchange = recore.amqp.MQ_CONF['EXCHANGE']
        self.ch.basic_publish(exchange=_exchange,
                              routing_key=plugin_queue,
                              body=json.dumps(msg),
                              properties=props)

        self.notify_step()
        self.app_logger.info("Dispatched job details for step %s" % this_step_name)
        self.app_logger.debug("Job details: %s" % msg)

        # Begin consuming from reply_queue. Wait for worker to update us
        for method, properties, body in self.ch.consume(self.reply_queue):
            self.ch.basic_ack(method.delivery_tag)
            self.ch.cancel()
            self.on_started(self.ch, method, properties, body)

    @method_wrapper
    def on_started(self, channel, method_frame, header_frame, body):
        _body = json.loads(body)
        self.app_logger.debug("Worker responded with: %s" % _body)

        if _body['status'] != 'started':
            # Let's get off this train. The plugin aborted and we don't
            # want to hang around any more. Leave the currently active
            # step where it is, move the remaining steps to 'skipped',
            # and then skip ahead to the on_ended method. Forward our
            # current "errored/failed" message to it.
            self.app_logger.error(
                "Received failure/error message from the worker: %s" % (
                    _body))
            self.failed = True
            self.on_ended(channel, method_frame, header_frame, body)
        else:
            self.app_logger.debug("Worker 'started' update received. "
                                  "Waiting for next state update")

            # Consume from reply_queue, wait for completed/errored message
            for method, properties, body in self.ch.consume(self.reply_queue):
                self.ch.basic_ack(method.delivery_tag)
                self.ch.cancel()
                self.on_ended(self.ch, method, properties, body)

    @method_wrapper
    def on_ended(self, channel, method_frame, header_frame, body):
        msg = json.loads(body)
        self.app_logger.debug("Got completed/errored message back from the worker: %s" % msg)
        self.notify_step(msg)

        # Remove from active step, push onto completed steps
        # - Reflect in MongoDB
        if msg['status'] == 'completed':
            self.app_logger.info("Completion update received from worker")
            self.move_active_to_completed()
            self._run()
        else:
            self.app_logger.error("Failure/error update received from worker")
            self.failed = True
            self.move_remaining_to_skipped()

    @method_wrapper
    def move_active_to_completed(self):
        finished_step = self.active_step
        self.active_sequence['completed_steps'].append(finished_step)
        self.active_step = None
        self.filter.set_field("active_step", "")
        _update_state = {
            '$set': {
                'active_step': self.active_step,
                'active_sequence': self.active_sequence
            }
        }
        self.update_state(_update_state)

    @method_wrapper
    def move_remaining_to_skipped(self):
        """Most likely an error message has just arrived from a worker.

Record the failed/skipped items so they can be updated in the db. Then
update self by emptying out anything active or remaining. Reflect this
in the DB.
        """
        self.filter.set_field('deploy_phase', 'error-state-cleanup')
        failed_step = self.active_step
        failed_sequence = self.active_sequence
        skipped_sequences = self.execution

        self.active_step = None
        self.active_sequence = {}
        self.execution = []

        _update_state = {
            '$set': {
                'failed_step': failed_step,
                'failed_sequence': failed_sequence,
                'skipped_sequences': skipped_sequences,
                'execution': self.execution
            }
        }

        self.update_state(_update_state)
        # We've moved the remaining steps into the skipped steps
        # list. The next time the FSM loops it will enter its cleanup
        # method and then terminate.

        # Accept our fate and admit we are a failure (so we can log
        # this properly in the db)
        self.failed = True
        self.app_logger.warn("Recorded failed state in this FSM instance")

    @method_wrapper
    def dequeue_next_active_step(self, to='active_step'):
        """Take the next remaining step/sequence off the queue and move it
        into active step/sequence.

        Discussion: this method does the work required to iterate over
        the execution steps stored in N-many execution
        sequences. Quick review:

        A playbook consists of several elements, relevant to this
        discussion, is the 'execution' element. The value of
        'execution' is a list. Each item in the list is a dictionary
        describing an 'execution sequence', i.e., execution steps
        accompanied by supporting meta-data (what hosts to run them
        on, a description, etc...)

        Each execution sequence dict contains an element, 'steps',
        which is a list. If you're into visually representing
        datastructures, then a playbook with two execution sequences
        would look like this (omitting irrelevant keys):

        playbook = {
            'execution': [
                { 'steps': [ 'step1`, 'step2', ... ] },
                { 'steps': [ 'step1`, 'step2', ... ] }
            ]
        }

        The FSM initial state is pretty much undefined. Once _run() is
        called from run() we process the initial setup steps (such as
        querying the DB for the state document). This initializes the
        FSM.

        From there we can think of the routine as basically a directed
        graph where we cycle through _run() to
        dequeue_next_active_step (where we pop/push steps/sequences
        off of/on to the remaining/completed steps/sequences stacks),
        on_started, on_ended, and finally _run() again. This continues
        until the acceptance condition is met: A release is completed
        If And Only If no more steps remain in the active execution
        sequence, AND no more execution sequences remain.

        TODO: Fill in remaining logic discussion.

        TODO: Update logic to handle 'preflight' sections and the
        required concurrency.

        """
        self.filter.set_field('deploy_phase', 'execution')
        try:
            # Use the .get() so it's easy to continue if a step failed
            self.active_step = self.active_sequence.get('steps', []).pop(0)
        except IndexError:
            # We have exhaused this execution sequence of all release
            # steps. Time to move on to the next sequence.
            #
            # Move the current exec seq into executed.
            self.app_logger.debug("Ran out of steps in this execution sequence")
            self.executed.append(self.active_sequence)

            try:
                self.active_sequence = self.execution.pop(0)
                self.app_logger.info("Popped another exec seq off the 'execution' stack")
                self.active_sequence['completed_steps'] = []
            except IndexError:
                # An IndexError at this point means that we have
                # exhaused this playbook of all execution
                # sequences. In other words, we're done!
                self.app_logger.info("Ran all execution sequences.")
                _update_state = {
                    '$set': {
                        to: None,
                        'active_sequence': {},
                        'executed': self.executed,
                        'execution': self.execution
                    }
                }
                self.update_state(_update_state)
                # Caught in the _run() method. Signals that we're
                # ready to _cleanup().
                raise IndexError
            else:
                # No exceptions means that we successfully loaded the
                # next execution sequence. Now, let's run this method
                # again (yo dawg, I heard you like recursion) so we
                # can pop off the next active step, and update the DB
                # with the changed active/executed sequences and
                # steps.
                #
                # We'll return from *THIS* call to this method once
                # the recursion returns so we don't update the
                # database twice with incorrect information.
                _update_state = {
                    '$set': {
                        to: self.active_step,
                        'active_sequence': self.active_sequence,
                        'executed': self.executed,
                        'execution': self.execution
                    }
                }
                self.update_state(_update_state)
                self.dequeue_next_active_step()
                # Once the dequeue call returns we've updated the
                # active_step and sequence in the database.
                return

        _update_state = {
            '$set': {
                to: self.active_step,
                'active_sequence': self.active_sequence,
                'executed': self.executed,
                'execution': self.execution
            }
        }
        self.update_state(_update_state)

    @method_wrapper
    def notify(self, phase, msg=None):
        """Send some notifications. Allowed values for `phase` include:
'started', 'completed', and 'failed'.

The optional `msg` parameter allows you to provide a custom message.
        """
        if recore.amqp.CONF.get('PHASE_NOTIFICATION', None):
            taboot_url = recore.amqp.CONF['PHASE_NOTIFICATION']['TABOOT_URL'] % (
                self.state_id)

            if msg is not None:
                _msg = msg
            else:
                _msg = "Release %s %s. See %s" % (
                    self.state_id,
                    str(phase),
                    taboot_url)

            recore.amqp.send_notification(
                self.ch,
                recore.amqp.CONF['PHASE_NOTIFICATION']['TOPIC'],
                self.state_id,
                recore.amqp.CONF['PHASE_NOTIFICATION']['TARGET'],
                phase,
                _msg)
            return True
        else:
            return False

    @method_wrapper
    def notify_step(self, response=None):
        """A step may have a user-defined notification. If one is set this
        method will send the proper notification out for processing.

`response` - Leave as `None` for 'started' statuss. Pass in a dict of
the workers response for 'completed' and 'failed' notifications.

Returns `None` if no action was required. Else, returns `True`
        """
        if type(self.active_step) == str or \
           type(self.active_step) == unicode:
            # this is just a string step, no parameters defined at all
            return None

        _step_key = self.active_step.keys()[0]
        # Is there a notification defined?
        if 'notify' not in self.active_step[_step_key]:
            return None

        self.app_logger.info("Identifying current step phase to determine if a notification should be sent")
        # What phase are we in? What will we tell the world about that?
        _phase = None
        _msg = ""
        if response is None:
            _phase = 'started'
            _msg = "Started step: %s" % str(self.active_step)
        elif response.get('status', None) == 'started':
            _phase = 'started'
            _msg = "Started step: %s" % str(self.active_step)
        elif response.get('status', None) == 'completed':
            _phase = 'completed'
            _msg = "Completed step: %s with status: %s" % (
                str(self.active_step),
                str(response))
        elif response.get('status', None) == 'failed':
            _phase = 'failed'
            _msg = "Failed step: %s with status: %s" % (
                str(self.active_step),
                str(response))
        else:
            self.app_logger.error("Invalid phase given: %s" % str(response['status']))
            raise TypeError("Invalid 'status' parameter for step notification: %s" % str(response['status']))

        self.app_logger.debug("Identified current phase: %s" % _phase)

        # Is there a notification defined for this phase?
        _notif = self.active_step[_step_key]['notify'].get(_phase, None)
        if (_notif is None) or (_notif == {}):
            self.app_logger.debug("No notification requested for this phase: %s" % _phase)
            # No notification set for this phase, get out
            return None

        # One or more notifications ARE set for this phase
        i = 0
        transports = []
        for routing_key, target in _notif.iteritems():
            transports.append(routing_key)
            route_to_topic = "notify.%s" % routing_key
            recore.amqp.send_notification(
                self.ch,
                route_to_topic,
                self.state_id,
                target,
                _phase,
                _msg)
            i += 1

        self.app_logger.info("Sent %s notifications over transport(s): %s" % (
            i,
            ", ".join(transports)))
        return True

    @method_wrapper
    def update_state(self, new_state):
        """
        Update the state document in Mongo for this release
        """
        try:
            _id_update_state = self.state_coll.update(self._id,
                                                      new_state)

            if _id_update_state:
                self.app_logger.debug("Updated 'currently running' task")
            else:
                self.app_logger.error("Failed to update 'currently running' task")
                raise Exception("Failed to update 'currently running' task")
        except pymongo.errors.PyMongoError, pmex:
            self.app_logger.error(
                "Unable to update state with %s. "
                "Propagating PyMongo error: %s" % (new_state, pmex))
            raise pmex

    @method_wrapper
    def _cleanup(self):
        self.app_logger.debug("Entered cleanup routine")
        if not self._post_deploy_action():
            self.filter.set_field("deploy_phase", "")
            self.failed = True

        self.filter.set_field("deploy_phase", "cleanup")
        # Send ending notification
        status = 'failed'
        if not self.failed:
            status = 'completed'

        self.notify(status)

        self.app_logger.debug("Deleting temp queue (%s) and closing the connection" % self.reply_queue)
        self.ch.queue_delete(queue=self.reply_queue)
        self.conn.close()

        _update_state = {
            '$set': {
                'ended': dt.now(),
                'failed': self.failed
            }
        }

        try:
            self.update_state(_update_state)
            self.app_logger.debug("Recorded release end time: %s" %
                                  _update_state['$set']['ended'])
        except Exception, e:
            self.app_logger.error("Could not set 'ended' item in state document")
            raise e
        else:
            self.app_logger.debug("Cleaned up all leftovers. We should terminate next")
        self.app_logger.debug("Finished cleanup routine")

    @method_wrapper
    def _connect_mq(self):
        self.app_logger.debug("Opening AMQP connection for release with id: %s" % self.state_id)

        # TODO: Use the same bus client as core
        mq = recore.amqp.MQ_CONF

        (self._params, self._connection_string) = self._parse_connect_params(mq)

        connection = pika.BlockingConnection(self._params)
        self.app_logger.info("Connected to AMQP with connection params set as %s" %
                             self._connection_string)
        channel = connection.channel()
        self.app_logger.debug("Declaring exchange and temp queue")
        channel.exchange_declare(exchange=mq['EXCHANGE'],
                                 durable=True,
                                 exchange_type='topic')
        result = channel.queue_declare(queue='',
                                       exclusive=True,
                                       durable=False)
        self.reply_queue = result.method.queue
        return (channel, connection)

    @method_wrapper
    def _parse_connect_params(self, mq_config):
        """Parse the given dictionary ``mq_config``. Return connection params,
        and a properly formatted AMQP connection string with the
        password masked out.

        The default port for SSL/Non-SSL connections is selected
        automatically if port is not supplied. If a port is supplied
        then that port is used instead.

        SSL is false by default. Enabling SSL and setting a port
        manually will use the supplied port.
        """
        _ssl_port = 5671
        _non_ssl_port = 5672

        self._creds = pika.PlainCredentials(mq_config['NAME'], mq_config['PASSWORD'])

        # SSL is set to 'True' in the config file
        if mq_config.get('SSL', False):
            _ssl = True
            _ssl_qp = "?ssl=t&ssl_options={ssl_version=ssl.PROTOCOL_TLSv1}"
            # Use the provided port, or the default SSL port if no
            # port is supplied
            _port = mq_config.get('PORT', _ssl_port)
        else:
            _ssl = False
            _ssl_qp = '?ssl=f'
            # Use the provided port, or the default non-ssl connection
            # port if no port was supplied
            _port = mq_config.get('PORT', _non_ssl_port)

        con_params = pika.ConnectionParameters(
            host=mq_config['SERVER'],
            port=_port,
            virtual_host=mq_config['VHOST'],
            credentials=self._creds,
            ssl=_ssl,
            ssl_options={'ssl_version': ssl.PROTOCOL_TLSv1}
        )

        connection_string = 'amqp://%s:***@%s:%s%s%s' % (
            mq_config['NAME'], mq_config['SERVER'],
            _port, mq_config['VHOST'], _ssl_qp)

        return (con_params, connection_string)

    @method_wrapper
    def _setup(self):
        if not self.initialized:
            self.filter.set_field('deploy_phase', 'initialization')
        else:
            self.filter.set_field('deploy_phase', 'execution')

        try:
            self.state.update(recore.mongo.lookup_state(self.state_id, self.playbook_id))
        except TypeError:
            self.app_logger.error("The given state document could not be located: %s" % self.state_id)
            raise LookupError("The given state document could not be located: %s" % self.state_id)

        try:
            if not self.ch and not self.conn:
                self.app_logger.debug("Opening AMQP connection and channel for the first time")
                (self.ch, self.conn) = self._connect_mq()
        except Exception, e:
            self.app_logger.error("Couldn't connect to AMQP")
            raise e

        self.group = self.state['group']
        self.dynamic.update(self.state['dynamic'])
        self.active_step = self.state['active_step']
        self.execution = self.state['execution']
        self.executed = self.state['executed']
        self.active_sequence = self.state['active_sequence']
        self.db = recore.mongo.database
        self.state_coll = self.db['state']

        if not self.initialized:
            self.app_logger.info("Initializing FSM")
            # FSM just spun up, do those misc. one-time things
            self.filter.set_field("deploy_phase", "initialization")
            self.app_logger.info("Running first time tasks as part of initialization")
            if not self._first_run():
                self.filter.set_field('deploy_phase', 'error-state-cleanup')
                self.app_logger.error("A first-time task or pre-deploy check failed during FSM initialization")
                # The one-time things failed. STAHP EVERYTHING
                self.move_remaining_to_skipped()
            else:
                self.initialized = True
                self.app_logger.info("FSM initialized")
                self.filter.set_field('deploy_phase', 'execution')

    @method_wrapper
    def _first_run(self):
        """Things to do only on initialization.

Developer notes: Don't take any corrective post-failure actions here
(if any happen). Rather, if there is an issue (like a pre-deploy check
failing): log the error, set self.failed = True, send a notify() with
`phase` = 'failed' and `msg` as a descriptive string (hopefully
pre-checks will always return a 'msg' field you can just use here, and
then finally return False.

Once control returns to _setup() the False return code will trigger
moving all remaining steps into skipped and then end the release.
_cleanup() will take care of sending the final 'failed' phase
notification.

TODO: Get FSM to send notifications to the general purpose output
worker.

        """
        _update_state = {
            '$set': {
                'reply_to': self.reply_queue
            }
        }
        self.update_state(_update_state)

        self.pre_deploy_check = recore.amqp.CONF.get('PRE_DEPLOY_CHECK', [])
        self.post_deploy_action = recore.amqp.CONF.get('POST_DEPLOY_ACTION', [])

        ##############################################################
        # 'Starting up' phase notification
        self.notify('started')

        # Run the pre-deploy check. It will give us back False as soon
        # as the first failure is detected.
        self.filter.set_field("deploy_phase", "pre-deploy-check")
        self.app_logger.info("Running pre-deploy checks")
        if not self._pre_deploy_check():
            self.app_logger.warn("One of the pre-deploy checks failed")
            self.filter.set_field("deploy_phase", 'error-state-cleanup')
            return False

        ##############################################################
        # We made it through the first-run steps without a problem
        self.filter.set_field("deploy_phase", "")
        return True

    @method_wrapper
    def _pre_deploy_check(self):
        """This is the pre-deployment check that runs when the FSM first spins
up."""
        for pre_check_data in self.pre_deploy_check:
            pre_check_key = pre_check_data['NAME']
            props = pika.spec.BasicProperties()
            props.correlation_id = self.state_id
            props.reply_to = self.reply_queue

            parameters = pre_check_data.get('PARAMETERS', {})
            parameters['command'] = pre_check_data['COMMAND']
            parameters['subcommand'] = pre_check_data['SUBCOMMAND']
            step_name = "{CMD}:{SUB}".format(
                CMD=parameters['command'],
                SUB=parameters['subcommand'])
            self.filter.set_field("active_step", step_name)
            self.app_logger.info("Executing pre-deploy-check '%s's %s step" % (
                pre_check_key, step_name))

            msg = {
                'group': self.group,
                'parameters': parameters,
                'dynamic': self.dynamic,
                'notify': {}
            }
            plugin_routing_key = "worker.%s" % pre_check_data['COMMAND']

            self.ch.basic_publish(
                exchange=recore.amqp.MQ_CONF['EXCHANGE'],
                routing_key=plugin_routing_key,
                body=json.dumps(msg),
                properties=props)

            self.app_logger.debug("Sent pre-deploy check (%s) new job details: %s" % (
                step_name, msg))
            # Begin consuming from reply_queue

            ##########################################################
            # First, consume and look for customary {status: started} message
            self.app_logger.debug("Waiting for pre-deploy to update us with initial startup status")
            check_failed = False
            for method, properties, body in self.ch.consume(self.reply_queue):
                # Stop consuming
                self.ch.cancel()

                _body = json.loads(body)
                if _body.get('status', '') != "started":
                    check_failed = True
                else:
                    self.app_logger.debug("Received good start-up message from worker")
                break

            if check_failed:
                # get outta-here -- something blew up. And because the
                # worker already failed, that's the only message we'll
                # receive from them so we don't need to consume any
                # more messages yet.
                self.failed = True
                self.filter.set_field("active_step", "")
                self.app_logger.error("Aborting the release because pre-deploy check {CHECK_NAME} failed during worker start-up".format(
                    CHECK_NAME=step_name))
                return False

            ##########################################################
            # Now we consume the final result message from the
            # worker. This is the part that tells us if they actually
            # finished the step, and if the result matches what we
            # expect.
            self.app_logger.debug("Waiting for pre-deploy to update us with final pass/fail")
            for method, properties, body in self.ch.consume(self.reply_queue):
                # Stop consuming
                self.ch.cancel()

                # Verify results
                _body = json.loads(body)
                if not _body == pre_check_data['EXPECTATION']:
                    check_failed = True
                    self.app_logger.error("Pre-deploy check failed. Received response '%s'. "
                                          "Expected response: '%s'" % (
                                              str(_body),
                                              str(pre_check_data['EXPECTATION'])))
                    self.app_logger.error("Aborting release due to failed pre-deploy check")
                else:
                    self.app_logger.info("Pre-deploy check passed: %s" % (
                        str(_body)))
                # Seriously, stop consuming
                break

            if check_failed:
                # get outta-here if something blew up
                self.failed = True
                self.filter.set_field("active_step", "")
                return False

        ##############################################################
        # End the for loop over each check
        #
        # If we got this far then nothing failed. So let's return True
        self.filter.set_field("active_step", "")
        return True

    @method_wrapper
    def _post_deploy_action(self):
        """This is the post-deployment check that runs when the FSM is
preparing to finish a deployment."""
        self.filter.set_field("deploy_phase", "post-deploy-check")
        for post_check_data in self.post_deploy_action:
            post_check_key = post_check_data['NAME']
            self.app_logger.info('Executing post-deploy-action: %s' % (
                post_check_key))

            props = pika.spec.BasicProperties()
            props.correlation_id = self.state_id
            props.reply_to = self.reply_queue

            parameters = post_check_data.get('PARAMETERS', {})
            parameters['command'] = post_check_data['COMMAND']
            parameters['subcommand'] = post_check_data['SUBCOMMAND']
            step_name = "{CMD}:{SUB}".format(
                CMD=parameters['command'],
                SUB=parameters['subcommand'])
            self.filter.set_field("active_step", step_name)

            msg = {
                'group': self.group,
                'parameters': parameters,
                'dynamic': self.dynamic,
                'notify': {}
            }
            plugin_routing_key = "worker.%s" % post_check_data['COMMAND']

            self.ch.basic_publish(
                exchange=recore.amqp.MQ_CONF['EXCHANGE'],
                routing_key=plugin_routing_key,
                body=json.dumps(msg),
                properties=props)

            self.app_logger.debug("Sent post-deploy action (%s) new job details: %s" % (
                step_name, msg))

            ##########################################################
            # First, consume and look for customary {status: started} message
            self.app_logger.debug("Waiting for post-deploy action to update us with initial startup status")
            action_failed = False
            for method, properties, body in self.ch.consume(self.reply_queue):
                # Stop consuming
                self.ch.cancel()

                _body = json.loads(body)
                if _body.get('status', '') != "started":
                    action_failed = True
                    self.app_logger.error("Post-deploy failed during startup. Received response '%s'." % (
                        str(_body)))
                    self.app_logger.error("Aborting release due to failed post-deploy startup")
                else:
                    self.app_logger.debug("Post-deploy startup is good")
                # Seriously, stop consuming
                break

            if action_failed:
                # get outta-here -- something blew up. And because the
                # worker already failed, that's the only message we'll
                # receive from them so we don't need to consume any
                # more messages yet.
                self.failed = True
                self.filter.set_field("active_step", "")
                self.app_logger.error("Aborting the release because post-deploy action failed during worker start-up")
                return False

            self.app_logger.debug("Waiting for post-deploy to update us with pass/fail")

            for method, properties, body in self.ch.consume(self.reply_queue):
                # Stop consuming
                self.ch.cancel()

                # Verify results
                _body = json.loads(body)
                if not _body['status'] == 'completed':
                    action_failed = True
                    self.app_logger.error("Post-deploy failed. Received response '%s'." % (
                        str(_body)))
                    self.app_logger.error("Aborting release due to failed post-deploy")
                else:
                    self.app_logger.info("Post-deploy passed: %s" % (
                        str(_body)))
                # Seriously, stop consuming
                break

            if action_failed:
                # get outta-here if something blew up
                self.failed = True
                self.filter.set_field("active_step", "")
                return False

        ##############################################################
        # End the for loop over each check
        #
        # If we got this far then nothing failed. So let's return True
        self.filter.set_field("active_step", "")
        return True


def fsm_logger(playbook_id, state_id):
        """Initialize the FSM Loggers

By default, the FSM will log to the console and a single
logfile.

Per-Release logging:

Optionally, one may log the FSM activity for each release to a
separate file. This is done by configuring the re-core
'RELEASE_LOG_DIR' setting with the path to the log-holding directory.

If per-release logging is enabled, the log files will be created as:
RELEASE_LOG_DIR/FSM-STATE_ID.log

.. warning::

   Be sure the FSM has permission to write the specified
   directory. You won't find out it can't until the first release is
   attempted.

Params:
- state_id: The ID of the currently active release


.. todo:: Configure log levels via settings file
"""
        # re-use the pre-deployment 'recore.playbook.PBID' logger
        # filter because it has all the field information already
        pb_logger = 'recore.playbook.' + playbook_id
        filter = recore.contextfilter.get_logger_filter(pb_logger)

        # This is our actual logger object
        deploy_logger = logging.getLogger(pb_logger + '.deployment')
        deploy_logger.addFilter(filter)
        # Log at the same threshold that the main application logs at
        deploy_logger.setLevel(logging.getLogger('recore').getEffectiveLevel())

        try:
            # Initialize the per-release logging directory
            release_log = os.path.join(RELEASE_LOG_DIR, "FSM-%s.log" % state_id)
            release_handler = logging.FileHandler(os.path.realpath(release_log))
            release_handler.setFormatter(recore.constants.LOG_FORMATTER)
            deploy_logger.addHandler(release_handler)
        except IOError:
            raise IOError("FSM could not write to the per-release log directory: %s" % (
                str(RELEASE_LOG_DIR)))
        except:
            pass

        return deploy_logger
