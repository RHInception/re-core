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
from recore import mongo
from recore import amqp
from recore.fsm import FSM
import mock
import pika
import pika.exceptions
import pymongo

state_id = "123456abcdef"
_state = {
    'project': 'example project',
    'dynamic': {},
    'completed_steps': [],
    'active_step': {},
    'remaining_steps': []
}


class TestFsm(TestCase):
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
        temp_queue = 'amqp-test_queue123'
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




    # def test_update_state(self):
    #     """
    #     Verify that update_state inserts the proper information
    #     """
    #     db = mock.MagicMock()
    #     collection = mock.MagicMock()
    #     collection.update = mock.MagicMock(mock.MagicMock(return_value=12345))
    #     db.__getitem__.return_value = collection
    #     objectid = bson.ObjectId()

    #     for state in ('completed', 'failed'):
    #         mongo.update_state(db, objectid, state)

    #         db['state'].update.assert_called_once_with(
    #             {'_id': objectid},
    #             {'$push': {'step_log': state}})
    #         db['state'].update.reset_mock()

    # def test_update_state_with_error(self):
    #     """
    #     Make sure that if mongo errors out while updating a state
    #     we are notified with the proper exception
    #     """
    #     db = mock.MagicMock()
    #     collection = mock.MagicMock()
    #     collection.update = mock.MagicMock(
    #         side_effect=pymongo.errors.PyMongoError('test error'))
    #     db.__getitem__.return_value = collection
    #     objectid = bson.ObjectId()

    #     # We should get a PyMongoError
    #     self.assertRaises(
    #         pymongo.errors.PyMongoError,
    #         mongo.update_state, db, objectid, 'completed')
