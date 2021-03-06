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
from contextlib import nested
from bson.objectid import ObjectId
from recore import mongo
from recore import amqp
from recore.fsm import FSM
import datetime
import json
import logging
import mock
import pika
import pika.exceptions
import pymongo


temp_queue = 'amqp-test_queue123'
state_id = "123456abcdef"
TEST_PBID = "547e13f7feb98272d8c0bc30"
fsm__id = {'_id': ObjectId(state_id)}
_active_step_string = "juicer:Promote"
_active_step_dict = {
    "service:Restart": {
        "service": "megafrobber",
    }
}

MQ_CONF = {
    "SERVER": "amqp.example.com",
    "NAME": "username",
    "PASSWORD": "password",
    "EXCHANGE": "my_exchange",
    "VHOST": "/",
    "QUEUE": "re",
    "PORT": 5672
}

# For pre-deploy check tests
PRE_DEPLOY_CONF = {
    "PRE_DEPLOY_CHECK": [
        {
            "NAME": "Require Change Record",
            "COMMAND": "servicenow",
            "SUBCOMMAND": "getchangerecord",
            "PARAMETERS": {
                "project": "myproject",
                "some_filter": "to find the record"
            },
            "EXPECTATION": {
                "status": "completed",
                "data": {
                    "exists": True
                }
            }
        }
    ]
}

# For the send_notification tests
NOTIFICATION_CONF = {
    'PHASE_NOTIFICATION': {
        'TABOOT_URL': 'http://taboot.example.com/%s'
    }
}


def new_notify_step(*phases):
    _step = {
        "service:Restart": {
            "service": "megafrobber",
            "notify": {
            }
        }
    }
    for phase in phases:
        _step['service:Restart']['notify'][phase] = {
            "irc": ['#achannel'],
        }
    return _step

_state = {
    # Meta
    'reply_to': None,
    'group': None,
    'created': None,
    'ended': None,
    'failed': False,
    'dynamic': {},
    'playbook_id': None,
    'active_step': None,
    'execution': [],
    'executed': [],
    'active_sequence': {},
}

def new_active_sequence():
    return {
        "hosts": [ "bar.ops.example.com" ],
        "description": "frobnicate these lil guys",
        "steps": [
            "juicer:Promote",
            {
                "misc:Echo": {
                    "input": "This is a test message"
                }
            },
            {
                "frob:Nicate": {
                    "things": "all the things",
                }
            }
        ]
    }

def new_playbook():
    return {
        "group": "testgroup",
        "name": "testname",
        "execution": [
            new_active_sequence()
        ]
    }





UTCNOW = datetime.datetime.utcnow()
msg_started = {
    "status": "started"
}
msg_completed = {
    "status": "completed"
}
msg_errored = {
    "status": "errored"
}


class TestFsm(TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    @mock.patch('recore.fsm.pika.PlainCredentials')
    @mock.patch('recore.fsm.pika.channel.Channel')
    @mock.patch('recore.fsm.pika.BlockingConnection')
    def test__connect_mq(self, connection, channel, creds):
        """FSM connecting to AMQP sets its reply_queue attribute"""
        with mock.patch.dict('recore.fsm.recore.amqp.MQ_CONF', MQ_CONF):
            creds.return_value = mock.MagicMock(spec=pika.credentials.PlainCredentials, name="mocked creds")
            mocked_conn = mock.MagicMock(spec=pika.connection.Connection, name="mocked connection")
            mocked_channel = mock.MagicMock(spec=pika.channel.Channel, name="mocked channel")
            channel.return_value = mocked_channel
            channel.queue_declare.return_value.method.queue = temp_queue
            mocked_conn.channel.return_value = channel
            connection.return_value = mocked_conn

            f = FSM(TEST_PBID, state_id)
            (ch, conn) = f._connect_mq()
            self.assertEqual(f.reply_queue, temp_queue, msg="Expected %s for reply_queue, instead got %s" %
                             (temp_queue, f.reply_queue))

    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test__setup(self, send_notification):
        """Setup works with an existing state document"""
        f = FSM(TEST_PBID, state_id)
        # An AMQP connection hasn't been made yet

        msg_started = {'status': 'completed', 'data': {'exists': True}}

        consume_iter = [
            (mock.Mock(name="method_mocked"),
             mock.Mock(name="properties_mocked"),
             json.dumps(msg_started))
        ]

        f.conn = mock.Mock(pika.connection.Connection)
        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel

        with mock.patch('recore.mongo.database') as (
                mongo.database):
            mongo.database = mock.MagicMock(pymongo.database.Database)
            mongo.database.__getitem__.return_value = mock.MagicMock(pymongo.collection.Collection)

            with mock.patch('recore.mongo.lookup_state') as (
                    mongo.lookup_state):
                mongo.lookup_state.return_value = _state

                with mock.patch('recore.amqp.CONF') as notif_conf:
                    notif_conf = NOTIFICATION_CONF
                    set_field = mock.MagicMock()
                    filter = mock.MagicMock(return_value=set_field)
                    f.filter = filter
                    f._setup()
                    assert f.group == _state['group']

        # At the very end a notification should go out no matter what
        assert send_notification.call_count == 1
        assert send_notification.call_args[0][4] == 'started'

    @mock.patch('recore.fsm.recore.amqp.CONF')
    @mock.patch.object(FSM, 'move_remaining_to_skipped')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test__setup_failed_pre_deploy_check(self, send_notification, move_remaining, amqp_conf):
        """Setup fails with an existing state document and a failed pre-deploy check"""
        f = FSM(TEST_PBID, state_id)
        # An AMQP connection hasn't been made yet
        amqp_conf.get.return_value = PRE_DEPLOY_CONF['PRE_DEPLOY_CHECK']
        msg_started = {'status': 'completed', 'data': {'exists': False}}

        consume_iter = [
            (mock.Mock(name="method_mocked"),
             mock.Mock(name="properties_mocked"),
             json.dumps(msg_started))
        ]

        f.conn = mock.Mock(pika.connection.Connection)
        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel

        with mock.patch('recore.mongo.database') as (
                mongo.database):
            mongo.database = mock.MagicMock(pymongo.database.Database)
            mongo.database.__getitem__.return_value = mock.MagicMock(pymongo.collection.Collection)

            with mock.patch('recore.mongo.lookup_state') as (
                    mongo.lookup_state):
                mongo.lookup_state.return_value = _state

                with mock.patch('recore.amqp.MQ_CONF') as mq_conf:
                    mq_conf = MQ_CONF
                    set_field = mock.MagicMock()
                    filter = mock.MagicMock(return_value=set_field)
                    f.filter = filter
                    f._setup()
                    assert f.group == _state['group']

        # No matter where a release fails, 'move_remaining_to_skipped' will be called
        move_remaining.assert_called_once_with()
        # the first run/pre-deploy steps will record the failed state
        assert f.initialized == False

        # The starting phase notification will be sent
        assert send_notification.call_count == 1
        assert send_notification.call_args[0][4] == 'started'

        # After first_run finishes self.failed should be True
        with mock.patch('recore.amqp.MQ_CONF') as mq_conf:
            mq_conf = MQ_CONF
            f._cleanup()
        assert send_notification.call_count == 2
        assert send_notification.call_args[0][4] == 'failed'
        assert f.failed == True

    def test__setup_lookup_state_none(self):
        """if lookup_state returns None then a LookupError is raised"""
        f = FSM(TEST_PBID, state_id)

        with mock.patch('recore.mongo.database') as (
                mongo.database):
            mongo.database = mock.MagicMock(pymongo.database.Database)
            mongo.database.__getitem__.return_value = mock.MagicMock(pymongo.collection.Collection)

            with mock.patch('recore.mongo.lookup_state') as (
                    mongo.lookup_state):
                # Didn't find the state document in MongoDB
                mongo.lookup_state.return_value = None

                with self.assertRaises(LookupError):
                    set_field = mock.MagicMock()
                    filter = mock.MagicMock(return_value=set_field)
                    f.filter = filter
                    f._setup()

    def test__setup_amqp_connect_fails(self):
        """_setup raises exception if amqp connection can't be made"""
        f = FSM(TEST_PBID, state_id)
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
                    set_field = mock.MagicMock()
                    filter = mock.MagicMock(return_value=set_field)
                    f.filter = filter
                    f._setup()

    @mock.patch.object(FSM, '_post_deploy_action')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test__cleanup(self, send_notification, post_deploy):
        """Cleanup erases the needful"""
        f = FSM(TEST_PBID, state_id)
        f.ch = mock.Mock(pika.channel.Channel)
        f.conn = mock.Mock(pika.connection.Connection)
        f.reply_queue = temp_queue

        _update_state = {
            '$set': {
                'ended': UTCNOW,
                'failed': False
            }
        }

        with mock.patch.object(f, 'update_state', mock.Mock()) as (
                us):
            with mock.patch('recore.fsm.dt') as (
                    dt):
                dt.utcnow.return_value = UTCNOW

                with mock.patch('recore.amqp.CONF') as notif_conf:
                    notif_conf = NOTIFICATION_CONF
                    set_field = mock.MagicMock()
                    filter = mock.MagicMock(return_value=set_field)
                    f.filter = filter
                    f._cleanup()

            # update state set the ended item in the state doc.
            us.assert_called_with(_update_state)
            f.conn.close.assert_called_once_with()
            f.ch.queue_delete.assert_called_once_with(queue=temp_queue)

        # At the very end a notification should go out no matter what
        self.assertEqual(send_notification.call_count, 1)
        assert send_notification.call_args[0][4] == 'completed'
        post_deploy.assert_called_once()

    @mock.patch.object(FSM, '_post_deploy_action')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test__cleanup_post_failed(self, send_notification, post_deploy):
        """Cleanup marks release as failed if post deploy fails"""
        post_deploy.return_value = False
        f = FSM(TEST_PBID, state_id)
        f.ch = mock.Mock(pika.channel.Channel)
        f.conn = mock.Mock(pika.connection.Connection)
        f.reply_queue = temp_queue

        _update_state = {
            '$set': {
                'ended': UTCNOW,
                'failed': True
            }
        }

        with mock.patch.object(f, 'update_state', mock.Mock()) as (
                us):
            with mock.patch('recore.fsm.dt') as (
                    dt):
                with mock.patch('recore.amqp.CONF') as notif_conf:
                    notif_conf = NOTIFICATION_CONF
                    dt.utcnow.return_value = UTCNOW
                    set_field = mock.MagicMock()
                    filter = mock.MagicMock(return_value=set_field)
                    f.filter = filter
                    f._cleanup()

            # update state set the ended item in the state doc.
            us.assert_called_with(_update_state)
            f.conn.close.assert_called_once_with()
            f.ch.queue_delete.assert_called_once_with(queue=temp_queue)

        # At the very end a notification should go out no matter what
        self.assertEqual(send_notification.call_count, 1)
        assert send_notification.call_args[0][4] == 'failed'
        post_deploy.assert_called_once()

    @mock.patch.object(FSM, '_post_deploy_action')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test__cleanup_failed(self, send_notification, post_deploy):
        """Cleanup fails if update_state raises"""
        f = FSM(TEST_PBID, state_id)
        f.ch = mock.Mock(pika.channel.Channel)
        f.conn = mock.Mock(pika.connection.Connection)
        f.failed = True  # Testing the fail notification too

        with mock.patch.object(f, 'update_state',
                               mock.Mock(side_effect=Exception("derp"))) as (
                us_exception):
            with self.assertRaises(Exception):
                with mock.patch('recore.amqp.CONF') as notif_conf:
                    notif_conf = NOTIFICATION_CONF
                    set_field = mock.MagicMock()
                    filter = mock.MagicMock(return_value=set_field)
                    f.filter = filter
                    f._cleanup()

        # At the very end a notification should go out no matter what
        self.assertEqual(send_notification.call_count, 1)
        assert send_notification.call_args[0][4] == 'failed'
        post_deploy.assert_called_once()

    @mock.patch.object(FSM, '_post_deploy_action')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test__cleanup_failed_post_passes(self, send_notification, post_deploy):
        """Cleanup fails if update_state raises and post deploy passes"""
        post_deploy.return_value = True
        f = FSM(TEST_PBID, state_id)
        f.ch = mock.Mock(pika.channel.Channel)
        f.conn = mock.Mock(pika.connection.Connection)
        f.failed = True  # Testing the fail notification too

        with mock.patch.object(f, 'update_state',
                               mock.Mock(side_effect=Exception("derp"))) as (
                us_exception):
            with mock.patch('recore.amqp.CONF') as notif_conf:
                notif_conf = NOTIFICATION_CONF
                with self.assertRaises(Exception):
                    set_field = mock.MagicMock()
                    filter = mock.MagicMock(return_value=set_field)
                    f.filter = filter
                    f._cleanup()

        # At the very end a notification should go out no matter what
        self.assertEqual(send_notification.call_count, 1)
        assert send_notification.call_args[0][4] == 'failed'
        post_deploy.assert_called_once()

    def test_update_state(self):
        """State updating does the needful"""
        f = FSM(TEST_PBID, state_id)
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
        f = FSM(TEST_PBID, state_id)
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
        f = FSM(TEST_PBID, state_id)
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
        f = FSM(TEST_PBID, state_id)
        f.active_step = _active_step_string
        f.active_sequence = new_active_sequence()
        f.executed = []
        f.execution = new_playbook()['execution']

        _update_state = {
            '$set': {
                'active_step': _active_step_string,
                'active_sequence': f.active_sequence,
                'executed': [],
                'execution': new_playbook()['execution'],
            }
        }

        with mock.patch.object(f, 'update_state') as (
                us):
            set_field = mock.MagicMock()
            filter = mock.MagicMock(return_value=set_field)
            f.filter = filter
            f.dequeue_next_active_step()
            us.assert_called_once_with(_update_state)
            self.assertEqual(f.active_step, _active_step_string)

    def test_move_active_to_completed(self):
        """FSM can update after completing a step"""
        f = FSM(TEST_PBID, state_id)
        f.active_step = _active_step_string
        f.active_sequence = new_active_sequence()
        f.active_sequence['completed_steps'] = []
        f.executed = []
        f.execution = new_playbook()['execution']
        f.completed_steps = []

        # For .called_once_with()
        _update_state = {
            '$set': {
                'active_step': None,
                'active_sequence': f.active_sequence
            }
        }

        with mock.patch.object(f, 'update_state') as (us):
            set_field = mock.MagicMock()
            filter = mock.MagicMock(return_value=set_field)
            f.filter = filter
            f.move_active_to_completed()
            us.assert_called_once_with(_update_state)
            # TODO: Double check what this should evaluate to
            # self.assertEqual(f.active_sequence['completed_steps'], [active_step])

    @mock.patch.object(FSM, 'on_started')
    @mock.patch.object(FSM, 'dequeue_next_active_step')
    @mock.patch.object(FSM, '_setup')
    def test__run(self, setup, dequeue, on_started):
        """The _run() method can send a proper message to a worker"""
        f = FSM(TEST_PBID, state_id)
        f.reply_queue = temp_queue

        f.group = "mock tests"
        f.dynamic = {}
        f.active_step = _active_step_string
        f.active_sequence = new_active_sequence()
        f.execution = new_playbook()['execution']

        consume_iter = [(
            mock.Mock(name="method_mocked"),
            mock.Mock(name="properties_mocked"),
            json.dumps(msg_completed),
        )]

        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel

        with mock.patch('recore.amqp.MQ_CONF') as mq_conf:
            mq_conf = MQ_CONF
            set_field = mock.MagicMock()
            filter = mock.MagicMock(return_value=set_field)
            f.filter = filter
            f._run()

        setup.assert_called_once_with()
        dequeue.assert_called_once_with()
        f.ch.basic_ack.assert_called_once_with(consume_iter[0][0].delivery_tag)
        f.ch.cancel.assert_called_once_with()
        on_started.assert_called_once_with(f.ch, *consume_iter[0])

    @mock.patch.object(FSM, '_cleanup')
    @mock.patch.object(FSM, 'dequeue_next_active_step', mock.Mock(side_effect=IndexError))
    @mock.patch.object(FSM, '_setup')
    def test__run_finished(self, setup, cleanup):
        """When the FSM is out of steps it raises IndexError and calls _cleanup"""
        f = FSM(TEST_PBID, state_id)
        result = f._run()
        f._setup.assert_called_once_with()
        f.dequeue_next_active_step.assert_called_once_with()
        cleanup.assert_called_once_with()
        self.assertTrue(result)

    @mock.patch.object(FSM, '_pre_deploy_check')
    @mock.patch.object(FSM, 'on_ended')
    def test_on_started(self, ended, pdc):
        """Once started, the FSM waits for a response, and then calls on_ended"""
        pdc.return_value = True
        with nested(
                mock.patch('recore.mongo.lookup_state'),
                mock.patch('recore.mongo.database')
            ) as (lookup_state, database):

            lookup_state.return_value = _state.copy()
            # {
            #     'group': 'PROJECT',
            #     'dynamic': {},
            #     'completed_steps': [],
            #     'active_step': 'active_step',
            #     'remaining_steps': [],
            # }
            f = FSM(TEST_PBID, state_id)
            f.reply_queue = temp_queue
            f.group = 'GROUP'

            consume_iter = [
                (mock.Mock(name="method_mocked"),
                 mock.Mock(name="properties_mocked"),
                 json.dumps(msg_started))
            ]

            publish = mock.Mock()
            channel = mock.Mock()
            channel.consume.return_value = iter(consume_iter)
            channel.basic_publish = publish
            f.ch = channel
            f.conn = mock.Mock(pika.connection.Connection)

            set_field = mock.MagicMock()
            filter = mock.MagicMock(return_value=set_field)
            f.filter = filter
            f._setup()
            f.on_started(f.ch, *consume_iter[0])

            f.ch.basic_ack.assert_called_once_with(consume_iter[0][0].delivery_tag)
            f.ch.cancel.assert_called_once_with()
            f.on_ended.assert_called_once_with(f.ch, *consume_iter[0])

    @mock.patch.object(FSM, 'notify_step')
    @mock.patch.object(FSM, '_run')
    @mock.patch.object(FSM, 'move_active_to_completed')
    @mock.patch.object(FSM, 'move_remaining_to_skipped')
    def test_on_ended(self, run, move_completed, move_to_skipped, notify):
        """Once a step ends the FSM checks if it completed or else"""
        f = FSM(TEST_PBID, state_id)

        consume_completed = [
            mock.Mock(name="method_mocked"),
            mock.Mock(name="properties_mocked"),
            json.dumps(msg_completed)
        ]

        consume_errored = [
            mock.Mock(name="method_mocked"),
            mock.Mock(name="properties_mocked"),
            json.dumps(msg_errored)
        ]

        # First check in the case where the job completed
        result = f.on_ended(f.ch, *consume_completed)
        f.move_active_to_completed.assert_called_once_with()
        f._run.assert_called_once_with()

        # Check the case where the job ended not "completed"
        f.move_active_to_completed.reset_mock()
        f._run.reset_mock()

        result = f.on_ended(f.ch, *consume_errored)
        f.move_remaining_to_skipped.assert_called_once_with()
        self.assertFalse(f.move_active_to_completed.called)
        self.assertFalse(result)

    ##################################################################
    # Tests for user-defined per-step notifications
    ##################################################################
    # Most out most of the basic setup methods so we can focus the
    # tests on just the targeted area
    @mock.patch.object(FSM, '_setup')
    @mock.patch.object(FSM, 'dequeue_next_active_step')
    @mock.patch.object(FSM, 'on_started')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test_step_notification_started(self, send_notification, on_started, dequeue_step, setup):
        """Per-step notifications work when starting a step

Tests for the case where only one notification transport (irc, email, etc) is defined"""
        f = FSM(TEST_PBID, state_id)

        msg_started = {'status': 'started'}

        consume_iter = [
            (mock.Mock(name="method_mocked"),
             mock.Mock(name="properties_mocked"),
             json.dumps(msg_started))
        ]

        # Pre-test scaffolding. Hard-code some mocked out
        # attributes/variables because we're skipping the usual
        # initialization steps.
        f.conn = mock.Mock(pika.connection.Connection)
        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel
        f.active_sequence = {'hosts': ['localhost']}
        f.group = 'testgroup'
        f.dynamic = {}
        f.active_step = new_notify_step('started')

        # Run the method now. It should terminate when it reaches the
        # end of _run() with a call to a mocked out on_started()
        with mock.patch('recore.amqp.MQ_CONF') as mq_conf:
            mq_conf = MQ_CONF
            set_field = mock.MagicMock()
            filter = mock.MagicMock(return_value=set_field)
            f.filter = filter
            f._run()

        self.assertEqual(send_notification.call_count, 1)
        self.assertEqual(send_notification.call_args[0][1], 'notify.irc')
        self.assertEqual(send_notification.call_args[0][2], state_id)
        self.assertEqual(send_notification.call_args[0][3], ['#achannel'])
        self.assertEqual(send_notification.call_args[0][4], 'started')

    @mock.patch.object(FSM, '_run')
    @mock.patch.object(FSM, 'move_active_to_completed')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test_step_notification_completed(self, send_notification, move_active, run):
        """Per-step notifications work when a step is completed

Tests for the case where only one notification transport (irc, email, etc) is defined"""
        f = FSM(TEST_PBID, state_id)

        msg_completed = {'status': 'completed'}

        consume_iter = [
            (mock.Mock(name="method_mocked"),
             mock.Mock(name="properties_mocked"),
             json.dumps(msg_completed))
        ]

        # Pre-test scaffolding. Hard-code some mocked out
        # attributes/variables because we're skipping the usual
        # initialization steps.
        f.conn = mock.Mock(pika.connection.Connection)
        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel
        f.active_sequence = {'hosts': ['localhost']}
        f.group = 'testgroup'
        f.dynamic = {}
        f.active_step = new_notify_step('completed')

        # Run the ended method with a body having 'status' as completed
        f.on_ended(channel,
                   mock.Mock(name="method_mocked"),
                   mock.Mock(name="header_mocked"),
                   json.dumps(msg_completed))

        self.assertEqual(send_notification.call_count, 1)
        self.assertEqual(send_notification.call_args[0][1], 'notify.irc')
        self.assertEqual(send_notification.call_args[0][2], state_id)
        self.assertEqual(send_notification.call_args[0][3], ['#achannel'])
        self.assertEqual(send_notification.call_args[0][4], 'completed')

    @mock.patch.object(FSM, 'update_state')
    @mock.patch.object(FSM, '_setup')
    @mock.patch.object(FSM, 'move_remaining_to_skipped')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test_step_notification_failed(self, send_notification, move_remaining, setup, updatestate):
        """Per-step notifications work when a step fails

Tests for the case where only one notification transport (irc, email, etc) is defined"""
        f = FSM(TEST_PBID, state_id)

        msg_failed = {'status': 'failed'}

        consume_iter = [
            (mock.Mock(name="method_mocked"),
             mock.Mock(name="properties_mocked"),
             json.dumps(msg_failed))
        ]

        # Pre-test scaffolding. Hard-code some mocked out
        # attributes/variables because we're skipping the usual
        # initialization steps.
        f.conn = mock.Mock(pika.connection.Connection)
        f.executed = []
        f.execution = []
        f.state_coll = {}
        f.post_deploy_action = []
        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel
        f.active_sequence = {'hosts': ['localhost']}
        f.group = 'testgroup'
        f.dynamic = {}
        f.active_step = new_notify_step('failed')
        set_field = mock.MagicMock()
        filter = mock.MagicMock(return_value=set_field)
        f.filter = filter

        # Run the ended method with a body having 'status' as failed
        f.on_ended(channel,
                   mock.Mock(name="method_mocked"),
                   mock.Mock(name="header_mocked"),
                   json.dumps(msg_failed))

        self.assertEqual(send_notification.call_count, 1)
        self.assertEqual(send_notification.call_args[0][1], 'notify.irc')
        self.assertEqual(send_notification.call_args[0][2], state_id)
        self.assertEqual(send_notification.call_args[0][3], ['#achannel'])
        self.assertEqual(send_notification.call_args[0][4], 'failed')

    @mock.patch.object(FSM, '_setup')
    @mock.patch.object(FSM, 'dequeue_next_active_step')
    @mock.patch.object(FSM, 'on_started')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test_step_notification_started_no_notifications(self, send_notification, on_started, dequeue_step, setup):
        """Per-step notifications don't happen if no notifications are defined"""
        f = FSM(TEST_PBID, state_id)

        msg_started = {'status': 'started'}

        consume_iter = [
            (mock.Mock(name="method_mocked"),
             mock.Mock(name="properties_mocked"),
             json.dumps(msg_started))
        ]

        # Pre-test scaffolding. Hard-code some mocked out
        # attributes/variables because we're skipping the usual
        # initialization steps.
        f.conn = mock.Mock(pika.connection.Connection)
        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel
        f.active_sequence = {'hosts': ['localhost']}
        f.group = 'testgroup'
        f.dynamic = {}
        f.active_step = new_notify_step()

        # Run the method now. It should terminate when it reaches the
        # end of _run() with a call to a mocked out on_started()
        with mock.patch('recore.amqp.MQ_CONF') as mq_conf:
            mq_conf = MQ_CONF
            set_field = mock.MagicMock()
            filter = mock.MagicMock(return_value=set_field)
            f.filter = filter
            f._run()

        self.assertEqual(send_notification.call_count, 0)

    @mock.patch.object(FSM, '_setup')
    @mock.patch.object(FSM, 'dequeue_next_active_step')
    @mock.patch.object(FSM, 'on_started')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test_step_notification_started_two_transports(self, send_notification, on_started, dequeue_step, setup):
        """Per-step notifications happen for all defined transports

Tests for the case where multiple notification transports (irc, email, etc) are defined"""

        f = FSM(TEST_PBID, state_id)

        msg_started = {'status': 'started'}

        consume_iter = [
            (mock.Mock(name="method_mocked"),
             mock.Mock(name="properties_mocked"),
             json.dumps(msg_started))
        ]

        # Pre-test scaffolding. Hard-code some mocked out
        # attributes/variables because we're skipping the usual
        # initialization steps.
        f.conn = mock.Mock(pika.connection.Connection)
        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel
        f.active_sequence = {'hosts': ['localhost']}
        f.group = 'testgroup'
        f.dynamic = {}

        _step = {
            "service:Restart": {
                "service": "megafrobber",
                "notify": {
                    "started": {
                        "irc": ['#achannel'],
                        "email": ['notify@example.com']
                    }
                }
            }
        }

        f.active_step = _step

        # Run the method now. It should terminate when it reaches the
        # end of _run() with a call to a mocked out on_started()
        with mock.patch('recore.amqp.MQ_CONF') as mq_conf:
            mq_conf = MQ_CONF
            set_field = mock.MagicMock()
            filter = mock.MagicMock(return_value=set_field)
            f.filter = filter
            f._run()

        self.assertEqual(send_notification.call_count, 2)

    @mock.patch.object(FSM, 'move_remaining_to_skipped')
    @mock.patch.object(FSM, '_run')
    @mock.patch.object(FSM, 'move_active_to_completed')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test_step_notification_failed_before_started_received(self, send_notification, move_active, run, skipped):
        """Per-step notifications happen if a step fails when the worker attempts to start it"""
        f = FSM(TEST_PBID, state_id)

        msg_failed = {'status': 'failed'}

        consume_iter = [
            (mock.Mock(name="method_mocked"),
             mock.Mock(name="properties_mocked"),
             json.dumps(msg_failed))
        ]

        # Pre-test scaffolding. Hard-code some mocked out
        # attributes/variables because we're skipping the usual
        # initialization steps.
        f.conn = mock.Mock(pika.connection.Connection)
        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel
        f.active_sequence = {'hosts': ['localhost']}
        f.group = 'testgroup'
        f.dynamic = {}
        f.active_step = new_notify_step('failed')

        # Run the ended method with a body having 'status' as completed
        f.on_started(channel,
                   mock.Mock(name="method_mocked"),
                   mock.Mock(name="header_mocked"),
                   json.dumps(msg_failed))

        self.assertEqual(send_notification.call_count, 1)
        self.assertEqual(send_notification.call_args[0][1], 'notify.irc')
        self.assertEqual(send_notification.call_args[0][2], state_id)
        self.assertEqual(send_notification.call_args[0][3], ['#achannel'])
        self.assertEqual(send_notification.call_args[0][4], 'failed')

    @mock.patch.object(FSM, 'move_remaining_to_skipped')
    @mock.patch.object(FSM, '_run')
    @mock.patch.object(FSM, 'move_active_to_completed')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test_post_deploy_passed(self, send_notification, move_active, run, skipped):
        """Post-deploy action passes"""
        f = FSM(TEST_PBID, state_id)

        msg_completed = {'status': 'started'}

        consume_iter = [
            (mock.Mock(name="method_mocked"),
             mock.Mock(name="properties_mocked"),
             json.dumps(msg_completed))
        ]

        # Pre-test scaffolding. Hard-code some mocked out
        # attributes/variables because we're skipping the usual
        # initialization steps.
        f.conn = mock.Mock(pika.connection.Connection)
        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel
        f.active_sequence = {'hosts': ['localhost']}
        f.group = 'testgroup'
        f.dynamic = {}
        f.active_step = new_notify_step('failed')
        f.post_deploy_action = [
            {
                "NAME": "Update dates",
                "COMMAND": "servicenow",
                "SUBCOMMAND": "updatedates",
                "PARAMETERS": {
                    "foo": "bar"
                }
            }
        ]

        with mock.patch('recore.amqp.MQ_CONF') as mq_conf:
            mq_conf = MQ_CONF
            set_field = mock.MagicMock()
            filter = mock.MagicMock(return_value=set_field)
            f.filter = filter
            self.assertEqual(f._post_deploy_action(), True)

    @mock.patch.object(FSM, 'move_remaining_to_skipped')
    @mock.patch.object(FSM, '_run')
    @mock.patch.object(FSM, 'move_active_to_completed')
    @mock.patch('recore.fsm.recore.amqp.send_notification')
    def test_post_deploy_failed(self, send_notification, move_active, run, skipped):
        """Post-deploy action fails"""
        f = FSM(TEST_PBID, state_id)

        msg_failed = {'status': 'failed', 'data': {'reason': 'it broke'}}

        consume_iter = [
            (mock.Mock(name="method_mocked"),
             mock.Mock(name="properties_mocked"),
             json.dumps(msg_failed))
        ]

        # Pre-test scaffolding. Hard-code some mocked out
        # attributes/variables because we're skipping the usual
        # initialization steps.
        f.conn = mock.Mock(pika.connection.Connection)
        publish = mock.Mock()
        channel = mock.Mock()
        channel.consume.return_value = iter(consume_iter)
        channel.basic_publish = publish
        f.ch = channel
        f.active_sequence = {'hosts': ['localhost']}
        f.group = 'testgroup'
        f.dynamic = {}
        f.active_step = new_notify_step('failed')
        f.post_deploy_action = [
            {
                "NAME": "Update dates",
                "COMMAND": "servicenow",
                "SUBCOMMAND": "updatedates",
                "PARAMETERS": {
                    "foo": "bar"
                }
            }
        ]

        with mock.patch('recore.amqp.MQ_CONF') as mq_conf:
            mq_conf = MQ_CONF
            set_field = mock.MagicMock()
            filter = mock.MagicMock(return_value=set_field)
            f.filter = filter
            self.assertEqual(f._post_deploy_action(), False)
