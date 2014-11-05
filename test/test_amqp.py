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

import mock
import json
import pika

from . import TestCase, unittest

from recore import amqp


# Mocks
CONF = {
    "LOGFILE": "recore.log",
    "MQ": {
        "NAME": "username",
        "PASSWORD": "password",
        "SERVER": "127.0.0.1",
        "PORT": 12345,
        "EXCHANGE": "re",
        "QUEUE": "testqueue",
        "VHOST": "/"
    },
    "DB": {
	"SERVERS": [
	    "mongo01.example.com",
	    "mongo02.example.com"
	],
	"DATABASE": "re",
	"NAME": "lordmongo",
	"PASSWORD": "webscale",
	"PORT": 27017
    },
    "PHASE_NOTIFICATION": {
        "TABOOT_URL":  "http://example.com/taboot/%s/",
        "TOPIC": "notify.irc" ,
        "TARGET": ["#achannel", "someperson"]
    },
    "PRE_DEPLOY_CHECK": [{
       "Frob something": {
           "COMMAND": "frob",
           "SUBCOMMAND": "thething",
           "PARAMETERS": {
               "name": "frobmeister"
           },
           "EXPECTATION": {"status": "completed", "data": {"exists": True}}
       }
    }],
}

connection = mock.MagicMock('connection')
CORR_ID = 12345
REPLY_TO = 'me'
PROPERTIES = pika.spec.BasicProperties(
    correlation_id=CORR_ID,
    reply_to=REPLY_TO)
channel = mock.MagicMock()


class TestAMQP(TestCase):

    def tearDown(self):
        """
        Reset mocks.
        """
        connection.reset_mock()

    def test_winternewt_bus_client(self):
        """
        Verify using WinternewtBusClient provides us with a useable object.
        """
        with mock.patch('pika.ConnectionParameters'):
            with mock.patch('pika.SelectConnection'):
                result = amqp.WinternewtBusClient(CONF)
                call_args = pika.ConnectionParameters.call_args_list[0][1]
                assert call_args['host'] == CONF['MQ']['SERVER']
                call_args['credentials'].username == CONF['MQ']['NAME']
                call_args['credentials'].password == CONF['MQ']['PASSWORD']

    def test_winternewt_bus_client_run(self):
        """
        Verify using WinternewtBusClient.run opens a connection and starts
        the ioloop.
        """
        with mock.patch('pika.ConnectionParameters'):
            with mock.patch('pika.SelectConnection'):
                result = amqp.WinternewtBusClient(CONF)
                result.run()

                pika.SelectConnection.assert_called_once_with(
                   parameters=mock.ANY,
                   on_open_callback=result.on_connection_open,
                   stop_ioloop_on_close=False)

                pika.SelectConnection.ioloop.start.assert_called_once()

    def test_winternewt_bus_client_on_open(self):
        """
        Make sure that on_open chains properly
        """
        with mock.patch('pika.ConnectionParameters'):
            with mock.patch('pika.SelectConnection'):
                with mock.patch('pika.connection') as connection:
                    with mock.patch('recore.amqp.WinternewtBusClient.open_channel') as oc:
                        result = amqp.WinternewtBusClient(CONF)
                        result.run()
                        result.on_connection_open(connection)
                        oc.assert_called_once()

    def test_winternewt_on_channel_open(self):
        """
        Make sure that on_channel_open chains properly
        """
        with mock.patch('pika.connection.channel') as channel:
            with mock.patch('pika.ConnectionParameters'):
                with mock.patch('pika.SelectConnection'):
                    result = amqp.WinternewtBusClient(CONF)

                    consumer_tag = 1
                    channel.basic_consume.return_value = consumer_tag
                    data = result.on_channel_open(channel)

                    # Verify expected calls
                    channel.start_consuming.assert_called_once()

    def test_winternewt_send_notification(self):
        """
        Make sure that send_notification sends the proper message to the bus.
        """

        with mock.patch('pika.ConnectionParameters'):
            with mock.patch('pika.SelectConnection'):
                result = amqp.WinternewtBusClient(CONF)

                with mock.patch('pika.connection.channel') as channel:
                    result.send_notification(
                        channel,
                        'notify.test',
                        '123456',
                        ['someone'],
                        'started',
                        'my message')

                    expected_body = json.dumps({
                        'slug': 'my message',
                        'message': 'my message',
                        'phase': 'started',
                        'target': ['someone'],
                    })

                    assert channel.basic_publish.call_count == 1
                    assert channel.basic_publish.call_args[1]['routing_key'] == 'notify.test'
                    assert channel.basic_publish.call_args[1]['body'] == expected_body

    def test_job_create(self):
        """
        Verify when topic job.create is received the FSM handles it properly
        """
        group = 'testgroup'
        release_id = 12345
        playbook_id = "555544443333222211110000"
        body = '{"group": "%s", "dynamic": {}, "playbook_id": "%s"}' % (
            group, playbook_id)

        method = mock.MagicMock(routing_key='job.create')
        with mock.patch('recore.job.create') as amqp.recore.job.create:
            amqp.recore.job.create.release.return_value = release_id
            with mock.patch('recore.fsm') as amqp.recore.fsm:
                with mock.patch(
                        'recore.amqp.recore.job.create.recore.mongo'):
                    amqp.recore.job.create.recore.mongo.lookup_playbook = (
                        mock.MagicMock(return_value={''}))

                    # Make the call
                    amqp.receive(channel, method, PROPERTIES, body)

                    # Verify the items which should have triggered
                    amqp.recore.job.create.release.assert_called_once_with(
                        channel, playbook_id, REPLY_TO, {})
                    # Verify a new thread of the FSM is started for
                    # this one specific release
                    amqp.recore.fsm.FSM.call_count == 1

    def test_job_create_failure(self):
        """
        Verify when topic job.create is received with bad data it's
        handled properly
        """
        group = 'testgroup'
        body = '{"bad": "data"}'
        release_id = 12345

        method = mock.MagicMock(routing_key='job.create')
        with mock.patch('recore.job.create') as amqp.recore.job.create:
            amqp.recore.job.create.release.return_value = release_id
            with mock.patch('recore.fsm') as amqp.recore.fsm:
                with mock.patch(
                        'recore.amqp.recore.job.create.recore.mongo'):
                    amqp.recore.job.create.recore.mongo.lookup_playbook = (
                        mock.MagicMock(return_value={''}))

                    # Make the call
                    assert amqp.receive(
                        channel, method, PROPERTIES, body) is None

                    # Verify create release wasn't triggered
                    assert amqp.recore.job.create.release.call_count == 0
                    # Verify a new thread of the FSM is started for
                    # this one specific release
                    amqp.recore.fsm.FSM.call_count == 0

    def test_unknown_topic(self):
        """
        When the FSM gets an unknown topic, verify the message is ignored
        """
        group = 'testgroup'
        release_id = 12345
        body = {"group": group, "status": "completed"}
        method = mock.MagicMock(routing_key='unknown')

        with mock.patch('recore.job.create') as amqp.recore.job.create:
            amqp.recore.job.create.release.return_value = release_id
            with mock.patch('recore.fsm') as amqp.recore.fsm:
                # Make the call
                amqp.receive(channel, method, PROPERTIES, json.dumps(body))
                # No release calls should be made
                assert amqp.recore.job.create.release.call_count == 0
                assert amqp.recore.fsm.FSM.call_count == 0

    def test_job_create_with_invalid_json(self):
        """
        New job requests with invalid json don't crash the FSM
        """
        group = 'testgroup'
        release_id = 12345
        body = '{"group": %s, "status": "completed"' % group
        method = mock.MagicMock(routing_key='job.create')

        with mock.patch('recore.job.create') as amqp.recore.job.create:
            amqp.recore.job.create.release.return_value = release_id
            with mock.patch('recore.fsm') as amqp.recore.fsm:
                with mock.patch('recore.amqp.reject') as amqp.reject:
                    # Make the call
                    amqp.receive(channel, method, PROPERTIES, body)
                    # No release calls should be made
                    assert amqp.recore.job.create.release.call_count == 0
                    assert amqp.recore.fsm.FSM.call_count == 0
                    amqp.reject.assert_called_once_with(
                        channel, method, False)
