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

from . import TestCase, unittest

from recore.job import create

# Mocks
channel = mock.MagicMock()


class TestJobCreate(TestCase):

    def tearDown(self):
        """
        Reset mocks.
        """
        channel.reset_mock()

    def test_release_with_good_data(self):
        """
        Verify create.release works when everything is perfect
        """
        with mock.patch(
                'recore.job.create.recore.mongo') as create.recore.mongo:
            create.recore.mongo.lookup_project = mock.MagicMock(
                return_value={"project": "test"})
            create.recore.mongo.initialize_state = mock.MagicMock(
                return_value=1234567890)

            assert create.release(channel, 'test', 'replyto', {}) == "1234567890"
            channel.basic_publish.assert_called_with(
                exchange='',
                routing_key='replyto',
                body='{"id": "1234567890"}')

    def test_release_if_project_does_not_exist(self):
        """
        Verify create.release works properly if a project does not exist
        """

        with mock.patch(
                'recore.job.create.recore.mongo') as create.recore.mongo:
            create.recore.mongo.lookup_project = mock.MagicMock(
                return_value={})

            assert create.release(channel, 'test', 'replyto', {}) is None
            channel.basic_publish.assert_called_with(
                exchange='',
                routing_key='replyto',
                body='{"id": null}')
