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
import logging
import os.path
import threading
import pika.spec
import pika.exceptions
import pymongo.errors

RELEASE_LOG_DIR = None


class FSM(threading.Thread):
    """The re-core Finite State Machine to oversee the execution of
a playbooks's release steps."""

    def __init__(self, state_id, *args, **kwargs):
        """Not really overriding the threading init method. Just describing
        the parameters we expect to receive when initialized and
        setting up logging.

        `state_id` - MongoDB ObjectID of the document holding release steps
        """
        super(FSM, self).__init__(*args, **kwargs)
        self.app_logger = fsm_logger(state_id)
        # properties for later when we run() like the wind
        self.ch = None
        self.conn = None
        self.state_id = state_id
        self._id = {'_id': ObjectId(self.state_id)}
        self.initialized = False
        self.state = {}
        self.dynamic = {}
        self.reply_queue = None
        self.failed = False

    def run(self):  # pragma: no cover
        try:
            self._run()
        except pika.exceptions.ConnectionClosed:
            # Don't know why, but pika likes to raise this exception
            # when we intentionally close a connection...
            self.app_logger.debug("Closed AMQP connection")
        self.app_logger.info("Terminating")
        return True

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

        # Parse the step into a message for the worker queue
        props = pika.spec.BasicProperties()
        props.correlation_id = self.state_id
        props.reply_to = self.reply_queue
        params = {}
        notify = {}
        self.app_logger.info("Pre-processing next step: %s" % str(self.active_step))
        if type(self.active_step) == str or \
           type(self.active_step) == unicode:
            self.app_logger.info("Next step is a string. Split it and route it")
            (worker_queue, sep, subcommand) = self.active_step.partition(':')
        else:
            self.app_logger.info("Next step is a %s. We have some work to do..." % (
                type(self.active_step)))
            self.app_logger.info(self.active_step)
            _step_key = self.active_step.keys()[0]
            (worker_queue, sep, subcommand) = _step_key.partition(':')
            params = self.active_step[_step_key]
            notify.update(self.active_step.get('notify', {}))

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

        self.app_logger.info("Sent plugin (%s) new job details" % plugin_queue)
        self.app_logger.info("Details: %s" % (
            str(msg)))
        # Begin consuming from reply_queue
        self.app_logger.debug("Waiting for plugin to update us")

        for method, properties, body in self.ch.consume(self.reply_queue):
            self.ch.basic_ack(method.delivery_tag)
            self.ch.cancel()
            self.on_started(self.ch, method, properties, body)

    def on_started(self, channel, method_frame, header_frame, body):
        self.app_logger.debug("Plugin responded with: %s" % body)

        _body = json.loads(body)
        if _body['status'] != 'started':
            # Let's get off this train. The plugin aborted and we don't
            # want to hang around any more. Leave the currently active
            # step where it is, move the remaining steps to 'skipped',
            # and then skip ahead to the on_ended method. Forward our
            # current "errored/failed" message to it.
            self.app_logger.error(
                "Received failure/error message from the worker: %s" % (
                    body))
            self.failed = True
            self.on_ended(channel, method_frame, header_frame, body)
        else:
            self.app_logger.info("Plugin 'started' update received. "
                                 "Waiting for next state update")
            self.app_logger.debug("Waiting for completed/errored message")

            # Consume from reply_queue, wait for completed/errored message
            for method, properties, body in self.ch.consume(self.reply_queue):
                self.ch.basic_ack(method.delivery_tag)
                self.ch.cancel()
                self.on_ended(self.ch, method, properties, body)

    def on_ended(self, channel, method_frame, header_frame, body):
        self.app_logger.debug("Got completed/errored message back from the worker")

        msg = json.loads(body)
        self.app_logger.debug(json.dumps(msg))

        # Remove from active step, push onto completed steps
        # - Reflect in MongoDB
        if msg['status'] == 'completed':
            self.app_logger.info("State update received: Job finished without error")
            self.move_active_to_completed()
            self._run()
        else:
            self.app_logger.error("State update received: Job finished with error(s)")
            self.failed = True
            self.move_remaining_to_skipped()

    def move_active_to_completed(self):
        finished_step = self.active_step
        self.active_sequence['completed_steps'].append(finished_step)
        self.active_step = None

        _update_state = {
            '$set': {
                'active_step': self.active_step,
                'active_sequence': self.active_sequence
            }
        }
        self.update_state(_update_state)

    def move_remaining_to_skipped(self):
        """Most likely an error message has just arrived from a worker.

Record the failed/skipped items so they can be updated in the db. Then
update self by emptying out anything active or remaining. Reflect this
in the DB.
        """
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
        self.app_logger.debug("Recorded failed state in this FSM instance")
        self._cleanup()

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
                _msg = "Release %s %s. See %s." % (
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

    def _cleanup(self):
        # Send ending notification
        status = 'failed'
        if not self.failed:
            status = 'completed'

        self.notify(status)

        self.ch.queue_delete(queue=self.reply_queue)
        self.app_logger.debug("Deleted AMQP queue: %s" % self.reply_queue)
        self.conn.close()
        self.app_logger.debug("Closed AMQP connection")

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

    def _connect_mq(self):
        mq = recore.amqp.MQ_CONF
        creds = pika.credentials.PlainCredentials(mq['NAME'], mq['PASSWORD'])
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            host=str(mq['SERVER']),
            credentials=creds))
        self.app_logger.debug("Connection to MQ opened.")
        channel = connection.channel()
        self.app_logger.debug("MQ channel opened. Declaring exchange ...")
        channel.exchange_declare(exchange=mq['EXCHANGE'],
                                 durable=True,
                                 exchange_type='topic')
        self.app_logger.debug("Exchange declared.")
        result = channel.queue_declare(queue='',
                                       exclusive=True,
                                       durable=False)
        self.reply_queue = result.method.queue
        return (channel, connection)

    def _setup(self):
        try:
            self.state.update(recore.mongo.lookup_state(self.state_id))
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
            # FSM just spun up, do those misc. one-time things
            if not self._first_run():
                # The one-time things failed. STAHP EVERYTHING
                self.move_remaining_to_skipped()
            else:
                self.initialized = True

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

        ##############################################################
        # 'Starting up' phase notification
        self.notify('started')

        # Run the pre-deploy check. It will give us back False as soon
        # as the first failure is detected.
        if not self._pre_deploy_check():
            return False

        ##############################################################
        # We made it through the first-run steps without a problem
        return True

    def _pre_deploy_check(self):
        """This is the pre-deployment check that runs when the FSM first spins
up."""
        for pre_check in self.pre_deploy_check:
            (pre_check_key, pre_check_data) = pre_check.items()[0]
            self.app_logger.info('Executing pre-deploy-check %s' % (
                pre_check_key))

            props = pika.spec.BasicProperties()
            props.correlation_id = self.state_id
            props.reply_to = self.reply_queue

            parameters = pre_check_data.get('PARAMETERS', {})
            parameters['command'] = pre_check_data['COMMAND']
            parameters['subcommand'] = pre_check_data['SUBCOMMAND']
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

            self.app_logger.info("Sent pre-deploy check (%s) new job details" % (
                plugin_routing_key))
            self.app_logger.info("Details: %s" % (
                str(msg)))
            # Begin consuming from reply_queue
            self.app_logger.debug("Waiting for pre-deploy to update us with pass/fail")

            for method, properties, body in self.ch.consume(self.reply_queue):
                # Stop consuming
                self.ch.cancel()

                # Verify results
                _body = json.loads(body)
                if not _body == pre_check_data['EXPECTATION']:
                    self.failed = True
                    self.app_logger.error("Pre-deploy check failed. Received response '%s'."
                                          "Expected response: '%s'" % (
                                              str(_body),
                                              str(pre_check_data['EXPECTATION'])))
                    self.app_logger.error("Aborting release due to failed pre-deploy check")
                else:
                    self.app_logger.error("Pre-deploy check passed: %s" % (
                        str(_body)))
                # Seriously, stop consuming
                break

            if self.failed:
                # get outta-here if something blew up
                return False

        ##############################################################
        # End the for loop over each check
        #
        # If we got this far then nothing failed. So let's return True
        return True


def fsm_logger(state_id):

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
        _log_id = 'FSM-%s' % state_id
        _level = logging.INFO

        app_logger = logging.getLogger(_log_id)
        app_logger.setLevel(_level)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s:%(funcName)s:%(lineno)d - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        handler.setLevel(_level)
        app_logger.addHandler(handler)

        # Initialize the per-release logging directory
        try:
            release_log = os.path.join(RELEASE_LOG_DIR, "%s.log" % _log_id)
            release_handler = logging.FileHandler(os.path.realpath(release_log))
            release_handler.setFormatter(formatter)
            release_handler.setLevel(_level)
            app_logger.addHandler(release_handler)
        except IOError:
            raise IOError("FSM could not write to the per-release log directory: %s" % (
                str(RELEASE_LOG_DIR)))
        except:
            pass

        return app_logger
