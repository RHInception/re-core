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

class TestRecoreInit(TestCase):
    def setUp(self):
        self.config_file_dne = '/dev/ihopethisfiledoesntexist.json'
        self.config_file_invalid = './test/files/settings-example-invalid.json'
        self.config_file_valid = './test/files/settings-example.json'
        self.log_level = logging.INFO
        self.log_level_stdout = logging.DEBUG


    def test_start_logging(self):
        """Loggers are created with appropriate handlers associated"""
        recore.start_logging('/dev/null', self.log_level)
        _logcore = logging.getLogger('recore')
        _logcorestdout = logging.getLogger('recore.stdout')
        assert len(_logcore.handlers) == 1
        assert len(_logcorestdout.handlers) == 1
        self.assertEqual(_logcore.level, self.log_level,
                         msg="logcore level is actually %s but we wanted %s" % (_logcore.level, self.log_level))
        self.assertEqual(_logcorestdout.level, self.log_level_stdout,
                         msg="logcorestdout level is actually %s but we wanted %s" % (_logcorestdout.level, self.log_level_stdout))


    def test_parse_config(self):
        """An example configuration file can be parsed"""
        # Case 1: File does not exist
        with mock.patch('recore.start_logging'):
            with self.assertRaises(SystemExit):
                cfg = recore.parse_config(self.config_file_dne)
        # Case 2: File is not valid json
        with mock.patch('recore.start_logging'):
            with self.assertRaises(SystemExit):
                cfg = recore.parse_config(self.config_file_invalid)
        # Case 3: File exists and is valid json
        with mock.patch('recore.start_logging'):
            cfg = recore.parse_config(self.config_file_valid)

    @mock.patch('recore.mongo.connect')
    def test_init_mongo(self, mongo_connect):
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
            "PORT": 27017
        }
        recore.init_mongo(connect_params)

        # Verify that init_mongo sets the mongo module conn/db variables
        self.assertIs(recore.mongo.connection, connection)
        self.assertIs(recore.mongo.database, database)

    def test_init_amqp(self):
        pass

    def test_watch_the_queue(self):
        pass

    def test_main(self):
        pass
