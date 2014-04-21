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

import pika
import mock

from . import TestCase, unittest

from recore.job import step

# Mocks
CORR_ID = 12345
PROPERTIES = pika.spec.BasicProperties(correlation_id=CORR_ID)
channel = mock.MagicMock()


class TestJobStep(TestCase):

    def tearDown(self):
        """
        Reset mocks.
        """
        channel.reset_mock()

    def test_step(self):
        """
        Verify step.run works when everything is perfect
        """
        assert step.run(channel, 'test', PROPERTIES.correlation_id) is None
        call_args = channel.basic_publish.call_args[1]
        assert call_args['body'] == '{"project": "test"}'
        assert call_args['exchange'] == 're'
        assert call_args['routing_key'] == 'plugin.shexec.start'
        assert call_args['properties'].correlation_id == CORR_ID
