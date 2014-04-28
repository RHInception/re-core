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

import datetime
import pika
import mock

from . import TestCase, unittest


# Mocks
UTCNOW = datetime.datetime.utcnow()
PROPERTIES = pika.spec.BasicProperties(correlation_id=12345, app_id='shexec')

channel = mock.MagicMock()


# class TestJobStatus(TestCase):

#     def tearDown(self):
#         """
#         Reset mocks.
#         """
#         channel.reset_mock()

#     def test_update(self):
#         """
#         Verify status.update works when everything is perfect
#         """
#         with mock.patch(
#                 'recore.job.status.recore.mongo') as status.recore.mongo:
#             with mock.patch('recore.job.status.dt') as status.dt:
#                 status.dt = mock.MagicMock('datetime.datetime')
#                 status.dt.utcnow = mock.MagicMock(return_value=UTCNOW)

#                 assert status.update(
#                     channel, mock.MagicMock(), PROPERTIES, {}) is None
#                 status.recore.mongo.update_state.assert_called_with(
#                     status.recore.mongo.database,
#                     12345,
#                     {'timestamp': UTCNOW, 'plugin': 'shexec'})

#     def test_running(self):
#         """
#         Verify running passes the correct information to mongo
#         """
#         with mock.patch(
#                 'recore.job.status.recore.mongo') as status.recore.mongo:
#             assert status.running(PROPERTIES, True) is None

#             status.recore.mongo.mark_release_running.assert_called_with(
#                 status.recore.mongo.database,
#                 12345,
#                 True)

#             assert status.running(PROPERTIES, False) is None
#             status.recore.mongo.mark_release_running.assert_called_with(
#                 status.recore.mongo.database,
#                 12345,
#                 False)
