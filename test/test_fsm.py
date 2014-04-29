# Copyright (C) 2014 SEE AUTHORS FILE
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

from . import TestCase, unittest
from bson.objectid import ObjectId
from recore import mongo
from recore import amqp
from recore.fsm import FSM
import datetime
import logging
import mock
import pika
import pika.exceptions
import pymongo


temp_queue = 'amqp-test_queue123'
state_id = "123456abcdef"
fsm__id = {'_id': ObjectId(state_id)}
_state = {
    'project': 'example project',
    'dynamic': {},
    'completed_steps': [],
    'active_step': {},
    'remaining_steps': []
}
UTCNOW = datetime.datetime.utcnow()


class TestFsm(TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    @mock.patch('recore.fsm.pika.PlainCredentials')
    @mock.patch('recore.fsm.pika.channel.Channel')
    @mock.patch('recore.fsm.pika.BlockingConnection')
    @mock.patch('recore.fsm.recore.amqp.MQ_CONF')
    def test__connect_mq(self, mq_conf, connection, channel, creds):
        """FSM connecting to AMQP sets its reply_queue attribute"""
        mq_conf = {
            'NAME': 'user',
            'PASSWORD': 'pass',
            'SERVER': '127.0.0.1',
            'EXCHANGE': 'foochange'
        }
        creds.return_value = mock.MagicMock(spec=pika.credentials.PlainCredentials, name="mocked creds")
        mocked_conn = mock.MagicMock(spec=pika.connection.Connection, name="mocked connection")
        mocked_channel = mock.MagicMock(spec=pika.channel.Channel, name="mocked channel")
        channel.return_value = mocked_channel
        channel.queue_declare.return_value.method.queue = temp_queue
        mocked_conn.channel.return_value = channel
        connection.return_value = mocked_conn

        f = FSM(state_id)
        (ch, conn) = f._connect_mq()
        self.assertEqual(f.reply_queue, temp_queue, msg="Expected %s for reply_queue, instead got %s" %
                         (temp_queue, f.reply_queue))

    def test__setup(self):
        """Setup works with an existing state document"""
        f = FSM(state_id)
        # An AMQP connection hasn't been made yet
        f._connect_mq = mock.MagicMock(return_value=(mock.Mock(pika.channel.Channel),
                                      mock.Mock(pika.connection.Connection)))

        with mock.patch('recore.mongo.database') as (
                mongo.database):
            mongo.database = mock.MagicMock(pymongo.database.Database)
            mongo.database.__getitem__.return_value = mock.MagicMock(pymongo.collection.Collection)

            with mock.patch('recore.mongo.lookup_state') as (
                    mongo.lookup_state):
                mongo.lookup_state.return_value = _state

                f._setup()
                assert f.project == _state['project']

    def test__setup_lookup_state_none(self):
        """if lookup_state returns None then a LookupError is raised"""
        f = FSM(state_id)

        with mock.patch('recore.mongo.database') as (
                mongo.database):
            mongo.database = mock.MagicMock(pymongo.database.Database)
            mongo.database.__getitem__.return_value = mock.MagicMock(pymongo.collection.Collection)

            with mock.patch('recore.mongo.lookup_state') as (
                    mongo.lookup_state):
                # Didn't find the state document in MongoDB
                mongo.lookup_state.return_value = None

                with self.assertRaises(LookupError):
                    f._setup()

    def test__setup_amqp_connect_fails(self):
        """_setup raises exception if amqp connection can't be made"""
        f = FSM(state_id)
        f._connect_mq = mock.MagicMock(side_effect=pika.exceptions.AMQPError("Couldn't connect to AMQP"))

        with mock.patch('recore.mongo.database') as (
                mongo.database):
            mongo.database = mock.MagicMock(pymongo.database.Database)
            mongo.database.__getitem__.return_value = mock.MagicMock(pymongo.collection.Collection)

            with mock.patch('recore.mongo.lookup_state') as (
                    mongo.lookup_state):
                # Found the state document in MongoDB
                mongo.lookup_state.return_value = _state

                with self.assertRaises(pika.exceptions.AMQPError):
                    f._setup()


    def test__cleanup(self):
        """Cleanup erases the needful"""
        f = FSM(state_id)
        f.ch = mock.Mock(pika.channel.Channel)
        f.conn = mock.Mock(pika.connection.Connection)
        f.reply_queue = temp_queue

        _update_state = {
            '$set': {
                'ended': UTCNOW
            }
        }

        with mock.patch.object(f, 'update_state', mock.Mock()) as (
                us):
            with mock.patch('recore.fsm.dt') as (
                    dt):
                dt.now.return_value = UTCNOW
                f._cleanup()

            # update state set the ended item in the state doc.
            us.assert_called_with(_update_state)
            f.conn.close.assert_called_once_with()
            f.ch.queue_delete.assert_called_once_with(queue=temp_queue)

    def test__cleanup_failed(self):
        """Cleanup fails if update_state raises"""
        f = FSM(state_id)
        f.ch = mock.Mock(pika.channel.Channel)
        f.conn = mock.Mock(pika.connection.Connection)

        with mock.patch.object(f, 'update_state',
                               mock.Mock(side_effect=Exception("derp"))) as (
                us_exception):
            with self.assertRaises(Exception):
                f._cleanup()

    def test_update_state(self):
        """State updating does the needful"""
        f = FSM(state_id)
        f.state_coll = mock.MagicMock(spec=pymongo.collection.Collection,
                                      return_value=True)

        _update_state = {
            '$set': {
                'ended': UTCNOW
            }
        }

        # FSM Sets its state document ID attr properly
        self.assertEqual(f._id, fsm__id)

        f.update_state(_update_state)

        # FSM passes the needful to the update method
        f.state_coll.update.assert_called_once_with(fsm__id,
                                                    _update_state)

    def test_update_missing_state(self):
        """We notice if no document was found to update"""
        f = FSM(state_id)
        f.state_coll = mock.MagicMock(spec=pymongo.collection.Collection,
                                      return_value=True)

        f.state_coll.update.return_value = None

        _update_state = {
            '$set': {
                'ended': UTCNOW
            }
        }

        with self.assertRaises(Exception):
            f.update_state(_update_state)

    def test_update_state_mongo_failed(self):
        """We notice if mongo failed while updating state"""
        f = FSM(state_id)
        f.state_coll = mock.MagicMock(spec=pymongo.collection.Collection,
                                      return_value=True)

        mocked_update = mock.MagicMock(side_effect=pymongo.errors.PyMongoError)
        f.state_coll.update = mocked_update

        _update_state = {
            '$set': {
                'ended': UTCNOW
            }
        }

        with self.assertRaises(pymongo.errors.PyMongoError):
            f.update_state(_update_state)

    def test_dequeue_next_active_step(self):
        """The FSM can remove the next step and update Mongo with it"""
        f = FSM(state_id)
        f.remaining = ["Step 1", "Step 2"]

        _update_state = {
            '$set': {
                'active_step': "Step 1",
                'remaining_steps': ["Step 2"]
            }
        }

        with mock.patch.object(f, 'update_state') as (
                us):
            f.dequeue_next_active_step()
            us.assert_called_once_with(_update_state)
            self.assertEqual(f.active, "Step 1")

    def test_move_active_to_completed(self):
        """FSM can update after completing a step"""
        f = FSM(state_id)
        active_step = {"plugin": "not real"}
        f.active = active_step.copy()
        f.completed = []

        # For .called_once_with()
        _update_state = {
            '$set': {
                'active_step': None,
                'completed_steps': [active_step]
            }
        }

        with mock.patch.object(f, 'update_state') as (us):
            f.move_active_to_completed()
            us.assert_called_once_with(_update_state)
            self.assertEqual(f.active, None)
            self.assertEqual(f.completed, [active_step])

    @mock.patch.object(FSM, 'on_started')
    @mock.patch.object(FSM, 'dequeue_next_active_step')
    @mock.patch.object(FSM, '_setup')
    def test__run(self, setup, dequeue, on_started):
        """The _run() method can send a proper message to a worker"""
        f = FSM(state_id)
        f.reply_queue = temp_queue

        f.project = "mock tests"
        f.dynamic = {}
        f.active = {
            'plugin': 'fake',
            'parameters': {'no': 'parameters'}
        }
        consume_iter = [
            (mock.Mock(name="method_mocked"),
             mock.Mock(name="properties_mocked"),
             mock.Mock(name="body_mocked"))
         ]

        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel

        f._run()

        setup.assert_called_once_with()
        dequeue.assert_called_once_with()
        f.ch.basic_ack.assert_called_once_with(consume_iter[0][0].delivery_tag)
        f.ch.cancel.assert_called_once_with()
        on_started.assert_called_once_with(f.ch, *consume_iter[0])
