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

import json
import pika
import mock

from . import TestCase, unittest

from recore import receive

# Mocks
CORR_ID = 12345
REPLY_TO = 'me'
PROPERTIES = pika.spec.BasicProperties(
    correlation_id=CORR_ID,
    reply_to=REPLY_TO)
channel = mock.MagicMock()


class TestReceive(TestCase):

    def tearDown(self):
        """
        Reset mocks.
        """
        channel.reset_mock()

    def test_job_create(self):
        """
        Verify when topic job.create is received the FSM handles it properly
        """
        project = 'testproject'
        body = '{"project": "%s"}' % project
        release_id = 12345

        method = mock.MagicMock(routing_key='job.create')
        with mock.patch('recore.job.create') as receive.recore.job.create:
            receive.recore.job.create.release.return_value = release_id

            with mock.patch('recore.job.step') as receive.recore.job.step:
                with mock.patch(
                        'recore.receive.recore.job.create.recore.mongo'):
                    receive.recore.job.create.recore.mongo.lookup_project = (
                        mock.MagicMock(return_value={''}))

                    # Make the call
                    receive.receive(channel, method, PROPERTIES, body)

                    # Verify the items which should have triggered
                    receive.recore.job.create.release.assert_called_once_with(
                        channel, project, REPLY_TO)
                    receive.recore.job.step.run.assert_called_once_with(
                        channel, project, release_id)

    def test_release_step_failure(self):
        """
        Verify when topic release.step is sent to FSM as a failure
        things are handled properly
        """
        project = 'testproject'
        release_id = 12345
        body = {"project": project, "status": "failed"}
        method = mock.MagicMock(routing_key='release.step')
        with mock.patch('recore.job.status') as receive.recore.job.status:

            # Make the call
            receive.receive(channel, method, PROPERTIES, json.dumps(body))
            # Verify the items which should be triggered
            receive.recore.job.status.update.assert_called_once_with(
                channel, method, PROPERTIES, body)
            receive.recore.job.status.running.assert_called_once_with(
                PROPERTIES, False)

    def test_release_step_completed(self):
        """
        Verify when topic release.step is sent to FSM as completed
        things are handled properly
        """
        project = 'testproject'
        release_id = 12345
        body = {"project": project, "status": "completed"}
        method = mock.MagicMock(routing_key='release.step')
        with mock.patch('recore.job.status') as receive.recore.job.status:

            # Make the call
            receive.receive(channel, method, PROPERTIES, json.dumps(body))
            receive.recore.job.status.update.assert_called_once_with(
                channel, method, PROPERTIES, body)
            receive.recore.job.status.running.assert_called_once_with(
                PROPERTIES, False)

    def test_unknown_topic(self):
        """
        When the FSM gets an unknown topic, verify the message is ignored
        """
        project = 'testproject'
        release_id = 12345
        body = {"project": project, "status": "completed"}
        method = mock.MagicMock(routing_key='unknown')
        with mock.patch('recore.job.status') as receive.recore.job.status:

            # Make the call
            receive.receive(channel, method, PROPERTIES, json.dumps(body))
            # No release calls should be made
            assert receive.recore.job.status.update.call_count == 0
            assert receive.recore.job.status.running.call_count == 0
