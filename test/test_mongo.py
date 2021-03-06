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

import bson
import pymongo
import datetime
import mock
from contextlib import nested
from bson.objectid import ObjectId
from . import TestCase, unittest

from recore import mongo
import recore.fsm

# Mocks
UTCNOW = datetime.datetime.utcnow()
connection = mock.MagicMock('connection')

def new_active_sequence():
    return {
        "hosts": [ "bar.ops.example.com" ],
        "description": "frobnicate these lil guys",
        "steps": [
            "bigip:OutOfRotation",
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


def new_triggers():
    return [
        {
            "DESCRIPTION": "Sleep for a sec before CURLing",
            "WHEN": {
                "NEXT_COMMAND": "bigip"
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	}
    ]

def new_compound_triggers():
    return [
        {
            "DESCRIPTION": "Sleep for a sec before bigiping",
            "WHEN": {
                "NEXT_COMMAND": "bigip",
                "NEXT_SUBCOMMAND": "OutOfRotation"
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	}
    ]

def new_triggers_recursive():
    return [
        {
            "DESCRIPTION": "Sleep for a sec before bigip",
            "WHEN": {
                "NEXT_COMMAND": "bigip",
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	},
        {
            "DESCRIPTION": "Run a noop before we sleep",
            "WHEN": {
                "NEXT_COMMAND": "sleep",
            },
            "COMMAND": "noop",
            "SUBCOMMAND": "Whatever",
            "PARAMETERS": {}
	}
    ]

def new_compound_triggers_no_match_subcommand():
    return [
        {
            "DESCRIPTION": "Sleep for a sec before bigip",
            "WHEN": {
                "NEXT_COMMAND": "bigip",
                "NEXT_SUBCOMMAND": "InRotation"
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	}
    ]

def new_compound_triggers_no_match_command():
    return [
        {
            "DESCRIPTION": "Sleep for a sec before mod_jk",
            "WHEN": {
                "NEXT_COMMAND": "mod_jk",
                "NEXT_SUBCOMMAND": "OutOfRotation"
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	}
    ]

def new_triggers_two_triggers_compound_match():
    return [
        {
            "DESCRIPTION": "Sleep for a sec before frobbing the bigip",
            "WHEN": {
                "NEXT_COMMAND": "bigip"
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	},
        {
            "DESCRIPTION": "Sleep for a sec before frobbing",
            "WHEN": {
                "NEXT_COMMAND": "frob",
                "NEXT_SUBCOMMAND": "Nicate"
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	}
    ]

def new_triggers_two_triggers_compound_no_match():
    return [
        {
            "DESCRIPTION": "Sleep for a sec before frobbing the bigip",
            "WHEN": {
                "NEXT_COMMAND": "bigip"
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	},
        {
            "DESCRIPTION": "Sleep for a sec before frobbing",
            "WHEN": {
                "NEXT_COMMAND": "frob",
                "NEXT_SUBCOMMAND": "Uncate"
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	}
    ]


def new_triggers_two_triggers():
    return [
        {
            "DESCRIPTION": "Sleep for a sec before frobbing the bigip",
            "WHEN": {
                "NEXT_COMMAND": "bigip"
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	},
        {
            "DESCRIPTION": "Sleep for a sec before frobbing",
            "WHEN": {
                "NEXT_COMMAND": "frob"
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	}
    ]


def new_playbook():
    return {
        "group": "testgroup",
        "name": "testname",
        "execution": [
            new_active_sequence()
        ]
    }


def new_triggers_not_loaded():
    return [
        {
            "DESCRIPTION": "Sleep for a sec before CURLing",
            "WHEN": {
                "NEXT_COMMAND": "notinplaybook"
            },
            "COMMAND": "sleep",
            "SUBCOMMAND": "seconds",
            "PARAMETERS": {
                "seconds": 1
            }
	}

]

class TestMongo(TestCase):

    def tearDown(self):
        """
        Reset mocks.
        """
        connection.reset_mock()

    def test_connect(self):
        """
        Verify mongo connections work as expected
        """
        with mock.patch('recore.mongo.MongoClient') as mongo.MongoClient:
            mongo.MongoClient.return_value = connection

            user = "user"
            passwd = "password"
            host = "127.0.0.1"
            port = 1234
            db = "database"
            ssl = "true"

            result = mongo.connect(host, port, user, passwd, db, ssl)

            mongo.MongoClient.assert_called_with("mongodb://%s:%s@%s:%s/%s?ssl=%s" % (
                user, passwd, host, port, db, ssl))
            assert result[0] == connection
            assert result[1] == connection[db]

    def test_lookup_playbook(self):
        """
        Make sure looking up projects follows the correct path
        """
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.find_one = mock.MagicMock(return_value={"data": "here"})
        db.__getitem__.return_value = collection
        playbook = '555544443333222211110000'

        # With result
        assert mongo.lookup_playbook(db, playbook, '000000000000000007654321') == {"data": "here"}

        # No result
        collection.find_one = mock.MagicMock(return_value=None)
        assert mongo.lookup_playbook(db, playbook, '000000000000000007654321') is None

        # Error result is {}
        assert mongo.lookup_playbook({}, playbook, '000000000000000007654321') == {}

        # Invalid playbook id raises errors
        with self.assertRaises(bson.errors.InvalidId):
            mongo.lookup_playbook(db, '6', '000000000000000007654321')

    @mock.patch('recore.contextfilter.get_logger_filter')
    def test_initialize_state(self, logger_filter):
        """
        Make sure that creating the initial state uses proper data
        """
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.update = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        group = 'testgroup'
        user_id = 'justabro'

        with mock.patch('recore.mongo.lookup_playbook') as (
                mongo.lookup_playbook):
            mongo.lookup_playbook = mock.MagicMock()
            PLAYBOOK_ID = 1234567
            mongo.lookup_playbook.return_value = new_playbook()

            with mock.patch('recore.mongo.datetime.datetime') as (
                    mongo.datetime.datetime):
                mongo.datetime.datetime = mock.MagicMock('datetime')
                mongo.datetime.datetime.utcnow = mock.MagicMock(
                    return_value=UTCNOW)

                # initialize state adds the calling user's ID to the
                # state record. It pulls this from the contextfilter
                # attached to the current logger. We need to slip some
                # values in there while nobody is watching
                get_field = mock.Mock(return_value=user_id)
                filter = mock.Mock()
                filter.get_field = get_field
                logger_filter.return_value = filter

                mongo.initialize_state(db, PLAYBOOK_ID, '000000000000000007654321', dynamic={})
                db['state'].update.assert_called_once_with(
                    {
                        '_id': ObjectId('000000000000000007654321')
                    },
                    {
                        '$set': {
                            'executed': [],
                            'group': group,
                            'user_id': user_id,
                            'failed': False,
                            'created': UTCNOW,
                            'dynamic': {},
                            'triggers': [],
                            'active_sequence': {
                                'steps': [
                                    'bigip:OutOfRotation',
                                    {'misc:Echo': {'input': 'This is a test message'}},
                                    {'frob:Nicate': {'things': 'all the things'}}
                                ],
                                'completed_steps': [],
                                'hosts': ['bar.ops.example.com'],
                                'description': 'frobnicate these lil guys'
                            },
                            'ended': None,
                            'active_step': None,
                            'reply_to': None,
                            'execution': [],
                            'playbook_id': PLAYBOOK_ID
                        }
                    })

    @mock.patch('recore.contextfilter.get_logger_filter')
    def test_initialize_state_with_error(self, logger_filter):
        """
        Make sure that if mongo errors out we are notified with the
        proper exception
        """
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.update = mock.MagicMock(
            side_effect=pymongo.errors.PyMongoError('test error'))
        db.__getitem__.return_value = collection
        playbook = '555544443333222211110000'

        set_field = mock.Mock(return_value=None)
        filter = mock.Mock()
        filter.set_field = set_field
        logger_filter.return_value = filter

        # We should get a PyMongoError
        self.assertRaises(
            pymongo.errors.PyMongoError, mongo.initialize_state, db, playbook, '000000000000000007654321')

    ##################################################################
    # Step triggers be here. yarrrrrrrr
    @mock.patch('recore.contextfilter.get_logger_filter')
    def test_initialize_state_with_one_trigger(self, logger_filter):
        """
        NEXT_COMMAND trigger loads with just one
        """
        recore.fsm.TRIGGERS = new_triggers()
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.update = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        group = 'testgroup'
        user_id = 'justabro'

        with nested(
                mock.patch('recore.mongo.lookup_playbook'),
                mock.patch('recore.mongo.datetime.datetime')
        ) as (mongo.lookup_playbook,
              mongo.datetime.datetime):
            mongo.lookup_playbook = mock.MagicMock()
            PLAYBOOK_ID = 1234567
            mongo.lookup_playbook.return_value = new_playbook()

            mongo.datetime.datetime = mock.MagicMock('datetime')
            mongo.datetime.datetime.utcnow = mock.MagicMock(
                return_value=UTCNOW)

            get_field = mock.Mock(return_value=user_id)
            filter = mock.Mock()
            filter.get_field = get_field
            logger_filter.return_value = filter

            mongo.initialize_state(db, PLAYBOOK_ID, '000000000000000007654321', dynamic={})
            db['state'].update.assert_called_once_with(
                {'_id': ObjectId('000000000000000007654321')},
                {
                    '$set': {
                        'executed': [],
                        'group': group,
                        'user_id': user_id,
                        'failed': False,
                        'created': UTCNOW,
                        'dynamic': {},
                        'triggers': new_triggers(),
                        'active_sequence':
                        {
                            'steps': [
                                {'sleep:seconds': {'seconds': 1}},
                                'bigip:OutOfRotation',
                                {'misc:Echo': {'input': 'This is a test message'}},
                                {'frob:Nicate': {'things': 'all the things'}}
                            ],
                            'completed_steps': [],
                            'hosts': ['bar.ops.example.com'],
                            'description': 'frobnicate these lil guys'
                        },
                        'ended': None,
                        'active_step': None,
                        'reply_to': None,
                        'execution': [],
                        'playbook_id': PLAYBOOK_ID
                    }})

    @mock.patch('recore.contextfilter.get_logger_filter')
    def test_initialize_state_with_multiple_triggers(self, logger_filter):
        """
        NEXT_COMMAND trigger loads multiple triggers
        """
        recore.fsm.TRIGGERS = new_triggers_two_triggers()
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.update = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        group = 'testgroup'
        user_id = 'justabro'

        with nested(
                mock.patch('recore.mongo.lookup_playbook'),
                mock.patch('recore.mongo.datetime.datetime')
        ) as (mongo.lookup_playbook,
              mongo.datetime.datetime):
            mongo.lookup_playbook = mock.MagicMock()
            PLAYBOOK_ID = 1234567
            mongo.lookup_playbook.return_value = new_playbook()

            mongo.datetime.datetime = mock.MagicMock('datetime')
            mongo.datetime.datetime.utcnow = mock.MagicMock(
                return_value=UTCNOW)

            get_field = mock.Mock(return_value=user_id)
            filter = mock.Mock()
            filter.get_field = get_field
            logger_filter.return_value = filter

            mongo.initialize_state(db, PLAYBOOK_ID, '000000000000000007654321', dynamic={})
            db['state'].update.assert_called_once_with(
                {'_id': ObjectId('000000000000000007654321')},
                {
                    '$set': {
                        'executed': [],
                        'group': group,
                        'user_id': user_id,
                        'failed': False,
                        'created': UTCNOW,
                        'dynamic': {},
                        'triggers': new_triggers_two_triggers(),
                        'active_sequence':
                        {
                            'steps': [
                                {'sleep:seconds': {'seconds': 1}},
                                'bigip:OutOfRotation',
                                {'misc:Echo': {'input': 'This is a test message'}},
                                {'sleep:seconds': {'seconds': 1}},
                                {'frob:Nicate': {'things': 'all the things'}}
                            ],
                            'completed_steps': [],
                            'hosts': ['bar.ops.example.com'],
                            'description': 'frobnicate these lil guys'
                        },
                        'ended': None,
                        'active_step': None,
                        'reply_to': None,
                        'execution': [],
                        'playbook_id': PLAYBOOK_ID
                    }
                })

    @mock.patch('recore.contextfilter.get_logger_filter')
    def test_initialize_state_with_triggers_not_loaded(self, logger_filter):
        """
        NEXT_COMMAND doesn't load triggers if WHEN doesn't match
        """
        recore.fsm.TRIGGERS = new_triggers_not_loaded()
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.update = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        group = 'testgroup'
        user_id = 'justabro'

        with nested(
                mock.patch('recore.mongo.lookup_playbook'),
                mock.patch('recore.mongo.datetime.datetime')
        ) as (mongo.lookup_playbook,
              mongo.datetime.datetime):
            mongo.lookup_playbook = mock.MagicMock()
            PLAYBOOK_ID = 1234567
            mongo.lookup_playbook.return_value = new_playbook()

            mongo.datetime.datetime = mock.MagicMock('datetime')
            mongo.datetime.datetime.utcnow = mock.MagicMock(
                return_value=UTCNOW)

            get_field = mock.Mock(return_value=user_id)
            filter = mock.Mock()
            filter.get_field = get_field
            logger_filter.return_value = filter

            mongo.initialize_state(db, PLAYBOOK_ID, '000000000000000007654321', dynamic={})
            db['state'].update.assert_called_once_with(
                {'_id': ObjectId('000000000000000007654321')},
                {
                    '$set': {
                        'executed': [],
                        'group': group,
                        'user_id': user_id,
                        'failed': False,
                        'created': UTCNOW,
                        'dynamic': {},
                        'triggers': new_triggers_not_loaded(),
                        'active_sequence':
                        {
                            'steps': [
                                'bigip:OutOfRotation',
                                {'misc:Echo': {'input': 'This is a test message'}},
                                {'frob:Nicate': {'things': 'all the things'}}
                            ],
                            'completed_steps': [],
                            'hosts': ['bar.ops.example.com'],
                            'description': 'frobnicate these lil guys'
                        },
                        'ended': None,
                        'active_step': None,
                        'reply_to': None,
                        'execution': [],
                        'playbook_id': PLAYBOOK_ID
                    }})

    @mock.patch('recore.contextfilter.get_logger_filter')
    def test_initialize_state_with_one_compound_trigger(self, logger_filter):
        """
        NEXT_COMMAND trigger loads with compound WHEN statements
        """
        recore.fsm.TRIGGERS = new_compound_triggers()
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.update = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        group = 'testgroup'
        user_id = 'justabro'

        with nested(
                mock.patch('recore.mongo.lookup_playbook'),
                mock.patch('recore.mongo.datetime.datetime')
        ) as (mongo.lookup_playbook,
              mongo.datetime.datetime):
            mongo.lookup_playbook = mock.MagicMock()
            PLAYBOOK_ID = 1234567
            mongo.lookup_playbook.return_value = new_playbook()

            mongo.datetime.datetime = mock.MagicMock('datetime')
            mongo.datetime.datetime.utcnow = mock.MagicMock(
                return_value=UTCNOW)

            get_field = mock.Mock(return_value=user_id)
            filter = mock.Mock()
            filter.get_field = get_field
            logger_filter.return_value = filter

            mongo.initialize_state(db, PLAYBOOK_ID, '000000000000000007654321', dynamic={})
            db['state'].update.assert_called_once_with(
                {'_id': ObjectId('000000000000000007654321')},
                {
                    '$set': {
                        'executed': [],
                        'group': group,
                        'user_id': user_id,
                        'failed': False,
                        'created': UTCNOW,
                        'dynamic': {},
                        'triggers': new_compound_triggers(),
                        'active_sequence':
                        {
                            'steps': [
                                {'sleep:seconds': {'seconds': 1}},
                                'bigip:OutOfRotation',
                                {'misc:Echo': {'input': 'This is a test message'}},
                                {'frob:Nicate': {'things': 'all the things'}}
                            ],
                            'completed_steps': [],
                            'hosts': ['bar.ops.example.com'],
                            'description': 'frobnicate these lil guys'
                        },
                        'ended': None,
                        'active_step': None,
                        'reply_to': None,
                        'execution': [],
                        'playbook_id': PLAYBOOK_ID
                    }})

    @mock.patch('recore.contextfilter.get_logger_filter')
    def test_initialize_state_with_one_compound_trigger_no_match_subcommand(self, logger_filter):
        """
        NEXT_COMMAND trigger doesn't load if only the COMMAND WHEN expression matches
        """
        recore.fsm.TRIGGERS = new_compound_triggers_no_match_subcommand()
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.update = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        group = 'testgroup'
        user_id = 'justabro'

        with nested(
                mock.patch('recore.mongo.lookup_playbook'),
                mock.patch('recore.mongo.datetime.datetime')
        ) as (mongo.lookup_playbook,
              mongo.datetime.datetime):
            mongo.lookup_playbook = mock.MagicMock()
            PLAYBOOK_ID = 1234567
            mongo.lookup_playbook.return_value = new_playbook()

            mongo.datetime.datetime = mock.MagicMock('datetime')
            mongo.datetime.datetime.utcnow = mock.MagicMock(
                return_value=UTCNOW)

            get_field = mock.Mock(return_value=user_id)
            filter = mock.Mock()
            filter.get_field = get_field
            logger_filter.return_value = filter

            mongo.initialize_state(db, PLAYBOOK_ID, '000000000000000007654321', dynamic={})
            db['state'].update.assert_called_once_with(
                {'_id': ObjectId('000000000000000007654321')},
                {
                    '$set': {
                        'executed': [],
                        'group': group,
                        'user_id': user_id,
                        'failed': False,
                        'created': UTCNOW,
                        'dynamic': {},
                        'triggers': new_compound_triggers_no_match_subcommand(),
                        'active_sequence':
                        {
                            'steps': [
                                'bigip:OutOfRotation',
                                {'misc:Echo': {'input': 'This is a test message'}},
                                {'frob:Nicate': {'things': 'all the things'}}
                            ],
                            'completed_steps': [],
                            'hosts': ['bar.ops.example.com'],
                            'description': 'frobnicate these lil guys'
                        },
                        'ended': None,
                        'active_step': None,
                        'reply_to': None,
                        'execution': [],
                        'playbook_id': PLAYBOOK_ID
                    }})

    @mock.patch('recore.contextfilter.get_logger_filter')
    def test_initialize_state_with_one_compound_trigger_no_match_command(self, logger_filter):
        """
        NEXT_COMMAND trigger doesn't load if only the SUBCOMMAND WHEN expression matches
        """
        recore.fsm.TRIGGERS = new_compound_triggers_no_match_command()
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.update = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        group = 'testgroup'
        user_id = 'justabro'

        with nested(
                mock.patch('recore.mongo.lookup_playbook'),
                mock.patch('recore.mongo.datetime.datetime')
        ) as (mongo.lookup_playbook,
              mongo.datetime.datetime):
            mongo.lookup_playbook = mock.MagicMock()
            PLAYBOOK_ID = 1234567
            mongo.lookup_playbook.return_value = new_playbook()

            mongo.datetime.datetime = mock.MagicMock('datetime')
            mongo.datetime.datetime.utcnow = mock.MagicMock(
                return_value=UTCNOW)

            get_field = mock.Mock(return_value=user_id)
            filter = mock.Mock()
            filter.get_field = get_field
            logger_filter.return_value = filter

            mongo.initialize_state(db, PLAYBOOK_ID, '000000000000000007654321', dynamic={})
            db['state'].update.assert_called_once_with(
                {'_id': ObjectId('000000000000000007654321')},
                {
                    '$set': {
                        'executed': [],
                        'group': group,
                        'user_id': user_id,
                        'failed': False,
                        'created': UTCNOW,
                        'dynamic': {},
                        'triggers': new_compound_triggers_no_match_command(),
                        'active_sequence':
                        {
                            'steps': [
                                'bigip:OutOfRotation',
                                {'misc:Echo': {'input': 'This is a test message'}},
                                {'frob:Nicate': {'things': 'all the things'}}
                            ],
                            'completed_steps': [],
                            'hosts': ['bar.ops.example.com'],
                            'description': 'frobnicate these lil guys'
                        },
                        'ended': None,
                        'active_step': None,
                        'reply_to': None,
                        'execution': [],
                        'playbook_id': PLAYBOOK_ID
                    }})

    @mock.patch('recore.contextfilter.get_logger_filter')
    def test_initialize_state_with_multiple_triggers_compound_match(self, logger_filter):
        """
        NEXT_COMMAND trigger loads multiple triggers and one is a compound match
        """
        recore.fsm.TRIGGERS = new_triggers_two_triggers_compound_match()
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.update = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        group = 'testgroup'
        user_id = 'justabro'

        with nested(
                mock.patch('recore.mongo.lookup_playbook'),
                mock.patch('recore.mongo.datetime.datetime')
        ) as (mongo.lookup_playbook,
              mongo.datetime.datetime):
            mongo.lookup_playbook = mock.MagicMock()
            PLAYBOOK_ID = 1234567
            mongo.lookup_playbook.return_value = new_playbook()

            mongo.datetime.datetime = mock.MagicMock('datetime')
            mongo.datetime.datetime.utcnow = mock.MagicMock(
                return_value=UTCNOW)

            get_field = mock.Mock(return_value=user_id)
            filter = mock.Mock()
            filter.get_field = get_field
            logger_filter.return_value = filter

            mongo.initialize_state(db, PLAYBOOK_ID, '000000000000000007654321', dynamic={})
            db['state'].update.assert_called_once_with(
                {'_id': ObjectId('000000000000000007654321')},
                {
                    '$set': {
                        'executed': [],
                        'group': group,
                        'user_id': user_id,
                        'failed': False,
                        'created': UTCNOW,
                        'dynamic': {},
                        'triggers': new_triggers_two_triggers_compound_match(),
                        'active_sequence':
                        {
                            'steps': [
                                {'sleep:seconds': {'seconds': 1}},
                                'bigip:OutOfRotation',
                                {'misc:Echo': {'input': 'This is a test message'}},
                                {'sleep:seconds': {'seconds': 1}},
                                {'frob:Nicate': {'things': 'all the things'}}
                            ],
                            'completed_steps': [],
                            'hosts': ['bar.ops.example.com'],
                            'description': 'frobnicate these lil guys'
                        },
                        'ended': None,
                        'active_step': None,
                        'reply_to': None,
                        'execution': [],
                        'playbook_id': PLAYBOOK_ID
                    }})

    @mock.patch('recore.contextfilter.get_logger_filter')
    def test_initialize_state_with_multiple_triggers_compound_no_match(self, logger_filter):
        """
        NEXT_COMMAND trigger loads multiple triggers skips a non-matching compound
        """
        recore.fsm.TRIGGERS = new_triggers_two_triggers_compound_no_match()
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.update = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        group = 'testgroup'
        user_id = 'justabro'

        with nested(
                mock.patch('recore.mongo.lookup_playbook'),
                mock.patch('recore.mongo.datetime.datetime')
        ) as (mongo.lookup_playbook,
              mongo.datetime.datetime):
            mongo.lookup_playbook = mock.MagicMock()
            PLAYBOOK_ID = 1234567
            mongo.lookup_playbook.return_value = new_playbook()

            mongo.datetime.datetime = mock.MagicMock('datetime')
            mongo.datetime.datetime.utcnow = mock.MagicMock(
                return_value=UTCNOW)

            get_field = mock.Mock(return_value=user_id)
            filter = mock.Mock()
            filter.get_field = get_field
            logger_filter.return_value = filter

            mongo.initialize_state(db, PLAYBOOK_ID, '000000000000000007654321', dynamic={})
            db['state'].update.assert_called_once_with(
                {'_id': ObjectId('000000000000000007654321')},
                {
                    '$set': {
                        'executed': [],
                        'group': group,
                        'user_id': user_id,
                        'failed': False,
                        'created': UTCNOW,
                        'dynamic': {},
                        'triggers': new_triggers_two_triggers_compound_no_match(),
                        'active_sequence':
                        {
                            'steps': [
                                {'sleep:seconds': {'seconds': 1}},
                                'bigip:OutOfRotation',
                                {'misc:Echo': {'input': 'This is a test message'}},
                                {'frob:Nicate': {'things': 'all the things'}}
                            ],
                            'completed_steps': [],
                            'hosts': ['bar.ops.example.com'],
                            'description': 'frobnicate these lil guys'
                        },
                        'ended': None,
                        'active_step': None,
                        'reply_to': None,
                        'execution': [],
                        'playbook_id': PLAYBOOK_ID
                    }})

    @mock.patch('recore.contextfilter.get_logger_filter')
    def test_initialize_state_with_two_recursive_triggers(self, logger_filter):
        """
        NEXT_COMMAND trigger loads and then the next trigger is added as well
        """
        recore.fsm.TRIGGERS = new_triggers_recursive()
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.update = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        group = 'testgroup'
        user_id = 'justabro'

        with nested(
                mock.patch('recore.mongo.lookup_playbook'),
                mock.patch('recore.mongo.datetime.datetime')
        ) as (mongo.lookup_playbook,
              mongo.datetime.datetime):
            mongo.lookup_playbook = mock.MagicMock()
            PLAYBOOK_ID = 1234567
            mongo.lookup_playbook.return_value = new_playbook()

            mongo.datetime.datetime = mock.MagicMock('datetime')
            mongo.datetime.datetime.utcnow = mock.MagicMock(
                return_value=UTCNOW)

            get_field = mock.Mock(return_value=user_id)
            filter = mock.Mock()
            filter.get_field = get_field
            logger_filter.return_value = filter

            mongo.initialize_state(db, PLAYBOOK_ID, '000000000000000007654321', dynamic={})
            db['state'].update.assert_called_once_with(
                {'_id': ObjectId('000000000000000007654321')},
                {
                    '$set': {
                        'executed': [],
                        'group': group,
                        'user_id': user_id,
                        'failed': False,
                        'created': UTCNOW,
                        'dynamic': {},
                        'triggers': new_triggers_recursive(),
                        'active_sequence':
                        {
                            'steps': [
                                'noop:Whatever',
                                {'sleep:seconds': {'seconds': 1}},
                                'bigip:OutOfRotation',
                                {'misc:Echo': {'input': 'This is a test message'}},
                                {'frob:Nicate': {'things': 'all the things'}}
                            ],
                            'completed_steps': [],
                            'hosts': ['bar.ops.example.com'],
                            'description': 'frobnicate these lil guys'
                        },
                        'ended': None,
                        'active_step': None,
                        'reply_to': None,
                        'execution': [],
                        'playbook_id': PLAYBOOK_ID
                    }})
