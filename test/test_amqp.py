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
MQ = {
    'NAME': 'username',
    'PASSWORD': 'password',
    'SERVER': '127.0.0.1',
    'PORT': 12345,
    'EXCHANGE': 're',
    'QUEUE': 'testqueue'
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

    def test_init_amqp(self):
        """
        Verify using init_amqp provides us with a connection
        """
        with mock.patch('pika.ConnectionParameters'):
            with mock.patch('pika.SelectConnection'):
                result = amqp.init_amqp(MQ)
                call_args = pika.ConnectionParameters.call_args_list[0][1]
                assert call_args['host'] == MQ['SERVER']
                call_args['credentials'].username == MQ['NAME']
                call_args['credentials'].password == MQ['PASSWORD']

                pika.SelectConnection.assert_called_once_with(
                    parameters=mock.ANY,
                    on_open_callback=amqp.on_open)

                # The result is expected to be the same as a module global
                assert result == amqp.connection

    def test_on_open(self):
        """
        Make sure that on_open chains properly
        """
        with mock.patch('pika.connection') as connection:
            amqp.on_open(connection)
            connection.channel.assert_called_once_with(amqp.on_channel_open)

    def test_on_channel_open(self):
        """
        Make sure that on_channel_open chains properly
        """
        with mock.patch('pika.connection.channel') as channel:
            consumer_tag = 1
            channel.basic_consume.return_value = consumer_tag
            result = amqp.on_channel_open(channel)

            # Verify expected calls
            channel.exchange_declare.assert_called_once_with(
                exchange=MQ['EXCHANGE'],
                durable=True,
                exchange_type='topic')

            channel.basic_consume.assert_called_once_with(
                amqp.receive,
                queue=MQ['QUEUE'])

            assert result == consumer_tag

    def test_job_create(self):
        """
        Verify when topic job.create is received the FSM handles it properly
        """
        project = 'testproject'
        body = '{"project": "%s", "dynamic": {}}' % project
        release_id = 12345

        method = mock.MagicMock(routing_key='job.create')
        with mock.patch('recore.job.create') as amqp.recore.job.create:
            amqp.recore.job.create.release.return_value = release_id
            with mock.patch('recore.fsm') as amqp.recore.fsm:
                with mock.patch(
                        'recore.amqp.recore.job.create.recore.mongo'):
                    amqp.recore.job.create.recore.mongo.lookup_project = (
                        mock.MagicMock(return_value={''}))

                    # Make the call
                    amqp.receive(channel, method, PROPERTIES, body)

                    # Verify the items which should have triggered
                    amqp.recore.job.create.release.assert_called_once_with(
                        channel, project, REPLY_TO, {})
                    # Verify a new thread of the FSM is started for
                    # this one specific release
                    amqp.recore.fsm.FSM.call_count == 1

    def test_job_create_failure(self):
        """
        Verify when topic job.create is received with bad data it's
        handled properly
        """
        project = 'testproject'
        body = '{"bad": "data"}'
        release_id = 12345

        method = mock.MagicMock(routing_key='job.create')
        with mock.patch('recore.job.create') as amqp.recore.job.create:
            amqp.recore.job.create.release.return_value = release_id
            with mock.patch('recore.fsm') as amqp.recore.fsm:
                with mock.patch(
                        'recore.amqp.recore.job.create.recore.mongo'):
                    amqp.recore.job.create.recore.mongo.lookup_project = (
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
        project = 'testproject'
        release_id = 12345
        body = {"project": project, "status": "completed"}
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
        project = 'testproject'
        release_id = 12345
        body = '{"project": %s, "status": "completed"' % project
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
                        channel, method, True)
