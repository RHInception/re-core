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
import recore
import logging
import mock
import pika
import recore.fsm
from argparse import Namespace


class TestRecoreInit(TestCase):
    def setUp(self):
        self.config_file_dne = Namespace(config='/dev/ihopethisfiledoesntexist.json')
        self.config_file_invalid = Namespace(config='./test/files/settings-example-invalid.json')
        self.config_file_valid = Namespace(config='./test/files/settings-example.json')
        self.config_file_per_release_logging = Namespace(config='./test/files/settings-release-log-dir.json')

        # These act as if triggers were specified on the CLI
        self.config_file_good_triggers = Namespace(config='./test/files/settings-example.json',
                                                   triggers='./examples/triggers/triggers.trigger.json')
        self.config_file_invalid_json_triggers = Namespace(config='./test/files/settings-example.json',
                                                           triggers='./test/files/invalid.triggers.json')
        self.config_file_triggers_dne = Namespace(config='./test/files/settings-example.json',
                                                  triggers='/dev/ihopethisfiledoesntexist.json')

        # This is for a config file pointing to a bad trigger file
        self.config_file_points_to_bad_trigger_file = Namespace(config='./test/files/settings-invalid-triggers.json')
        self.log_level = logging.DEBUG

    def test_start_logging(self):
        """Loggers are created with appropriate handlers associated"""
        recore.start_logging('/dev/null', self.log_level)
        _logcore = logging.getLogger('recore')

        # Handlers, etc, are bumped to 4 because of testing
        self.assertEqual(len(_logcore.handlers), 14)
        self.assertEqual(len(_logcore.filters), 7)
        self.assertEqual(_logcore.level, self.log_level,
                         msg="logcore level is actually %s but we wanted %s" % (_logcore.level, self.log_level))

    def test_parse_config(self):
        """An example configuration file can be parsed"""
        # Case 1: File does not exist
        # with mock.patch('recore.start_logging'):
        with self.assertRaises(SystemExit):
            cfg = recore.parse_config(self.config_file_dne)
            assert recore.amq.MQ_CONF is {}

        # Case 2: File is not valid json
        # with mock.patch('recore.start_logging'):
        with self.assertRaises(SystemExit):
            cfg = recore.parse_config(self.config_file_invalid)
            assert recore.amq.CONF is {}
            assert recore.amq.MQ_CONF is {}

        # Case 3: File exists and is valid json
        # with mock.patch('recore.start_logging'):
        cfg = recore.parse_config(self.config_file_valid)
        assert recore.amqp.CONF is cfg
        assert recore.amqp.MQ_CONF is cfg['MQ']

    @mock.patch('recore.mongo.connect')
    def test_init_mongo(self, mongo_connect):
        """Verify mongo connections/databases are initialized and retained"""
        connection = mock.MagicMock('connection')
        database = mock.MagicMock('database')
        mongo_connect.return_value = (connection, database)
        connect_params = {
            "SERVERS": [
                "mongo01.example.com",
                "mongo02.example.com"
            ],
            "DATABASE": "re",
            "NAME": "lordmongo",
            "PASSWORD": "webscale",
            "PORT": 27017,
            "SSL": "true"
        }
        recore.mongo.init_mongo(connect_params)

        # Verify that init_mongo sets the mongo module conn/db variables
        self.assertIs(recore.mongo.connection, connection)
        self.assertIs(recore.mongo.database, database)

    def test_parse_config_triggers_good(self):
        """We can configure the FSM with triggers when they're defined"""
        cfg = recore.parse_config(self.config_file_good_triggers)
        assert recore.fsm.TRIGGERS != []

    def test_parse_config_triggers_invalid_json(self):
        """We gracefully exit if a trigger file is invalid"""
        with self.assertRaises(SystemExit):
            cfg = recore.parse_config(self.config_file_invalid_json_triggers)

    def test_parse_config_triggers_done_exist(self):
        """We gracefully exit if a specified trigger file doesn't exist"""
        with self.assertRaises(SystemExit):
            cfg = recore.parse_config(self.config_file_triggers_dne)

    def test_parse_config_file_triggers_points_to_bad_triggers_file(self):
        """We gracefully exit if the main config file points to a bad triggers file"""
        with self.assertRaises(SystemExit):
            cfg = recore.parse_config(self.config_file_points_to_bad_trigger_file)

    def test_parse_config_per_release_log_dir(self):
        """The FSM is configured if RELEASE_LOG_DIR is set"""
        cfg = recore.parse_config(self.config_file_per_release_logging)
        self.assertEqual(recore.fsm.RELEASE_LOG_DIR, '/tmp/fsm')
