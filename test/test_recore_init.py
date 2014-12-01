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


class TestRecoreInit(TestCase):
    def setUp(self):
        self.config_file_dne = '/dev/ihopethisfiledoesntexist.json'
        self.config_file_invalid = './test/files/settings-example-invalid.json'
        self.config_file_valid = './test/files/settings-example.json'
        self.log_level = logging.DEBUG

    def test_start_logging(self):
        """Loggers are created with appropriate handlers associated"""
        recore.start_logging('/dev/null', self.log_level)
        _logcore = logging.getLogger('recore')

        # Handlers, etc, are bumped to 4 because of testing
        self.assertEqual(len(_logcore.handlers), 4)
        self.assertEqual(len(_logcore.filters), 2)
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

    #
    # Combined connect_mq with init_amqp. Need to refacter this unit test
    #
    #
    # @mock.patch.object(pika, 'channel')
    # @mock.patch('recore.amqp.connect_mq')
    # def test_init_amqp(self, connect_mq, mock_channel):
    #     """We can connect to AMQP properly"""
    #     connection = mock.MagicMock(pika.connection)
    #     channel = mock_channel
    #     queue = mock.PropertyMock(return_value='maiqueue')
    #     method = mock.Mock()
    #     type(method).queue = queue
    #     type(channel).method = method
    #     channel.queue_declare.return_value = method
    #     print "Print mocked properties: %s" % channel.method.queue

    #     connect_mq.return_value = (channel, connection)
    #     connect_params = {
    #         "SERVER": "amqp.example.com",
    #         "PASSWORD": "password",
    #         "EXCHANGE": "my_exchange",
    #         "PORT": 12345,
    #         "NAME": "foobar",
    #         "QUEUE": "maiqueue"
    #     }
    #     #channel.queue_declare.return_value = method
    #     (_channel, _connection, _queue_name) = recore.amqp.init_amqp(connect_params)

    #     # Check the calls we expect
    #     _cp = {}
    #     for k,v in connect_params.iteritems():
    #         _cp[k.lower()] = v
    #     del _cp['queue']
    #     del _cp['port']

    #     recore.amqp.connect_mq.assert_called_once_with(**_cp)
    #     channel.queue_declare.assert_called_once_with(durable=True, queue=connect_params['QUEUE'])

    #     # Check results
    #     assert _channel == channel
    #     assert _connection == connection
    #     #print "Queue name: %s | ConnectParams['QUEUE']: %s" % \
    #     #    (_queue_name, connect_params['QUEUE'])
    #     #assert _queue_name == connect_params['QUEUE']
    #     #
    #     # I can't for the life of me figure out how to make the
    #     # queue_name check work.... skip it for now.

    # Combined receive with 'watch the queue'. Need to update this unit test
    #
    #
    # def test_watch_the_queue(self):
    #     """
    #     Verify that consuming happens when watch_the_queue is called.
    #     """
    #     channel = mock.MagicMock('channel')
    #     channel.basic_consume = mock.MagicMock('basic_consume')
    #     channel.start_consuming = mock.MagicMock('start_consuming')
    #     connection = mock.MagicMock('connection')
    #     queue_name = 'maiqueu'

    #     # Fake callback for consumed messages
    #     cb = lambda x: type(x)

    #     # Call the tested function
    #     recore.amqp.watch_the_queue(channel, connection, queue_name, callback=cb)

    #     # Verify calls are made
    #     channel.basic_consume.assert_called_once_with(
    #         recore.receive.receive,
    #         queue=queue_name,
    #         no_ack=True,
    #         callback=cb)

    #     channel.start_consuming.assert_called_once_with()
