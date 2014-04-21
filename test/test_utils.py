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

from recore import utils

# Mocks
channel = mock.MagicMock()
connection = mock.MagicMock()
connection.channel = mock.MagicMock(return_value=channel)


class TestUtils(TestCase):

    def tearDown(self):
        """
        Reset mocks.
        """
        channel.reset_mock()

    def test_create_json_str(self):
        """
        Verify create_json_str produces proper json
        """
        assert utils.create_json_str({'test': 'data'}) == '{"test": "data"}'
        assert utils.create_json_str({'test': None}) == '{"test": null}'
        self.assertRaises(ValueError, utils.create_json_str, "BAD DATA")

    def test_load_json_str(self):
        """
        Verify load_json_str produces proper structures
        """
        assert utils.load_json_str('{"test": "data"}') == {'test': 'data'}
        assert utils.load_json_str('{"test": null}') == {'test': None}
        self.assertRaises(ValueError, utils.load_json_str, "BAD DATA")

    def test_connect_mq(self):
        """
        Check that connect_mq follows the expected connection steps
        """

        with mock.patch(
                'pika.BlockingConnection') as utils.pika.BlockingConnection:
            utils.pika.BlockingConnection.return_value = connection
            name = "name"
            server = "127.0.0.1"
            password = "password"
            exchange = "exchange"
            result = utils.connect_mq(
                name=name, password=password,
                server=server, exchange=exchange)

            assert result[0] == channel
            assert result[1] == connection
            connection_params = utils.pika.BlockingConnection.call_args[0][0]
            assert connection_params.host == server
            assert connection_params.credentials.username == name
            assert connection_params.credentials.password == password

            channel.exchange_declare.assert_called_with(
                exchange=exchange,
                durable=True,
                exchange_type='topic')

    def test_parse_config_file(self):
        """
        Verify config parsing works as expected.
        """
        self.assertRaises(IOError, utils.parse_config_file, 'doesnotexist')
        result = utils.parse_config_file('examples/settings-example.json')
        assert type(result) is dict
