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
import recore.job.step
import recore.amqp
import logging
import threading
import pika.spec
import pymongo.errors

class FSM(threading.Thread):
    """The re-core Finite State Machine to oversee the execution of
a project's release steps."""

    def __init__(self, state_id, *args, **kwargs):
        """Not really overriding the threading init method. Just describing
        the parameters we expect to receive when initialized and
        setting up logging.

        `state_id` - MongoDB ObjectID of the document holding release steps
        """
        super(FSM, self).__init__(*args, **kwargs)
        self.app_logger = logging.getLogger('FSM-%s' % state_id)
        self.app_logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)
        self.app_logger.addHandler(handler)

        # properties for later when we run() like the wind
        self.state_id = state_id
        self.state = {}
        self.dynamic = {}
        self.reply_queue = None

    def run(self):
        self._run()

    def _run(self):
        self._setup()
        try:
            # Pop a step off the remaining steps queue
            # - Reflect in MongoDB
            # Mark step as active in MongoDB
            self.dequeue_next_active_step()
            self.app_logger.info("Dequeued next active step. Updated currently active step.")
        except IndexError:
            # The previous step was the last step
            self.app_logger.info("Processed all remaining steps for job with id: %s" % self.state_id)
            self.app_logger.info("Cleaning up after release")
            # Now that we're done, clean up that queue
            self._cleanup()
            return True

        # Parse the step into a message for the worker queue
        props = pika.spec.BasicProperties()
        props.correlation_id = self.state_id
        props.reply_to = self.reply_queue

        params = self.active['parameters']
        #required_dynamic = self.active.get('dynamic', [])
        msg = {
            'project': self.project,
            'params': params,
            'dynamic': self.dynamic
        }
        plugin_queue = "worker.%s" % self.active['plugin']

        # Send message to the worker with instructions
        self.ch.basic_publish(exchange='',
                              routing_key=plugin_queue,
                              body=json.dumps(msg),
                              properties=props)

        self.app_logger.info("Sent message with topic '%s' and body: %s" % \
                             (plugin_queue, str(json.dumps(msg))))

        # Begin consuming from reply_queue
        self.app_logger.info("Waiting for plugin to update us")

        for method, properties, body in self.ch.consume(self.reply_queue):
            self.ch.cancel()
            self.on_started(self.ch, method, properties, body)

        # self.ch.basic_consume(self.on_started,
        #                       queue=self.reply_queue,
        #                       no_ack=True)

        # Eventually we go through enough callbacks that we end up
        # calling _run() again

    def on_started(self, channel, method_frame, header_frame, body):
        # Got it!
        channel.basic_ack(delivery_tag=method_frame.delivery_tag)
        # Stop consuming so we don't short circuit the state machine
        # channel.basic_cancel(consumer_tag=method_frame.consumer_tag)

        self.app_logger.info("Plugin started update received:")
        self.app_logger.info(body)
        self.app_logger.info("Waiting for completed/errored message")

        # Consume from reply_queue, wait for completed/errored message
        for method, properties, body in self.ch.consume(self.reply_queue):
            self.ch.cancel()
            self.on_ended(self.ch, method, properties, body)

    def on_ended(self, channel, method_frame, header_frame, body):
        self.app_logger.info("Got completed/errored message back from the worker")
        # Got it!
        channel.basic_ack(delivery_tag=method_frame.delivery_tag)
        # Stop consuming so we don't short circuit the state machine
        #channel.basic_cancel(consumer_tag=method_frame.consumer_tag)

        msg = json.loads(body)
        self.app_logger.info(json.dumps(msg))

        # Remove from active step, push onto completed steps
        # - Reflect in MongoDB
        if msg['status'] == 'completed':
            self.app_logger.info("Job finished")
            self.move_active_to_completed()
            self._run()
        else:
            self.app_logger.info("Job failed")
            raise Exception("Job failed!")

    def move_active_to_completed(self):
        try:
            finished_step = self.active
            self.completed.append(finished_step)
            self.active = None

            _update_state = {
                '$set': {
                    'active_step': self.active,
                    'completed_steps': self.completed
                }
            }

            _id = {'_id': ObjectId(self.state_id)}
            _id_update_state = self.state_coll.update(_id,
                                                  _update_state)

            if _id_update_state:
                self.app_logger.info("Updated currently running task")
            else:
                self.app_logger.error("Failed to update running task")
        except pymongo.errors.PyMongoError, pmex:
            out.error(
                "Unable to update state with %s. "
                "Propagating PyMongo error: %s" % (_update_state, pmex))
            raise pmex

    def dequeue_next_active_step(self):
        """Take the next remaining step off the queue and move it into active
        steps.
        """
        try:
            self.active = self.remaining.pop(0)
            _id = {'_id': ObjectId(self.state_id)}
            _update_active_step = {
                '$set': {
                    'active_step': self.active
                }
            }
            _update_remaining_steps = {
                '$set': {
                    'remaining_steps': self.remaining
                }
            }
            _id_active = self.state_coll.update(_id, _update_active_step)
            _id_remaining = self.state_coll.update(_id, _update_remaining_steps)
            if _id_active and _id_remaining:
                self.app_logger.info("Updated currently running task")
            else:
                self.app_logger.error("Failed to update running task")
        except pymongo.errors.PyMongoError, pmex:
            out.error(
                "Unable to update state with %s. "
                "Propagating PyMongo error: %s" % (_update, pmex))
            raise pmex

    def _cleanup(self):
        self.ch.queue_delete(queue=self.reply_queue)
        self.conn.close()
        _id = {'_id': ObjectId(self.state_id)}
        _update_state = {
            '$set': {
                'ended': dt.now()
            }
        }

        try:
            _update_id = self.state_coll.update(_id, _update_state)

            if _update_id:
                self.app_logger.info("Set 'ended' item in state document")
            else:
                self.app_logger.error("Could not set 'ended' item in state document")
        except pymongo.errors.PyMongoError, pmex:
            out.error(
                "Unable to update state with %s. "
                "Propagating PyMongo error: %s" % (_update, pmex))
            raise pmex

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
        return (channel, connection)

    def _setup(self):
        print "Updating state for: %s" % self.state_id
        self.app_logger.info("Updating state for: %s" % self.state_id)
        try:
            self.state.update(recore.mongo.lookup_state(self.state_id))
        except TypeError, te:
            self.app_logger.error("The given state document could not be located: %s" % self.state_id)
            raise LookupError("The given state document could not be located: %s" % self.state_id)

        try:
            # (self.conn, self.ch) = recore.amqp.connect_mq(**recore.amqp.MQ_CONF)
            (self.ch, self.conn) = self._connect_mq()
        except Exception, e:
            self.app_logger.info("Failed to connect to AMQP with: %s" % str(recore.amqp.MQ_CONF))
            self.app_logger.error("Couldn't connect to AMQP: %s" % str(e))

        self.project = self.state['project']
        self.dynamic.update(self.state['dynamic'])
        self.reply_queue = self.state['reply_to']
        self.completed = self.state['completed_steps']
        self.active = self.state['active_step']
        self.remaining = self.state['remaining_steps']
        self.db = recore.mongo.database
        self.state_coll = self.db['state']
