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

import bson
import pymongo
import datetime
import mock

from . import TestCase, unittest

from recore import mongo


# Mocks
UTCNOW = datetime.datetime.utcnow()
connection = mock.MagicMock('connection')


class TestMongo(TestCase):

    def tearDown(self):
        """
        Reset mocks.
        """
        connection.reset_mock()

    def test_connect(self):
        """
        Verify mongo connections work as expected
        """
        with mock.patch('recore.mongo.MongoClient') as mongo.MongoClient:
            mongo.MongoClient.return_value = connection

            user = "user"
            passwd = "password"
            host = "127.0.0.1"
            port = 1234
            db = "database"

            result = mongo.connect(host, port, user, passwd, db)

            mongo.MongoClient.assert_called_with("mongodb://%s:%s@%s:%s/%s" % (
                user, passwd, host, port, db))
            assert result[0] == connection
            assert result[1] == connection[db]

    def test_lookup_playbook(self):
        """
        Make sure looking up projects follows the correct path
        """
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.find_one = mock.MagicMock(return_value={"data": "here"})
        db.__getitem__.return_value = collection
        playbook = '555544443333222211110000'

        # With result
        assert mongo.lookup_playbook(db, playbook) == {"data": "here"}

        # No result
        collection.find_one = mock.MagicMock(return_value=None)
        assert mongo.lookup_playbook(db, playbook) is None

        # Error result is {}
        assert mongo.lookup_playbook({}, playbook) == {}

    def test_initialize_state(self):
        """
        Make sure that creating the initial state uses proper data
        """
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.insert = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        group = 'testgroup'

        with mock.patch('recore.mongo.lookup_playbook') as (
                mongo.lookup_playbook):
            mongo.lookup_playbook = mock.MagicMock()
            PLAYBOOK_ID = 1234567
            mongo.lookup_playbook.return_value = {
                '_id': PLAYBOOK_ID,
                'group': group
            }

            with mock.patch('recore.mongo.datetime.datetime') as (
                    mongo.datetime.datetime):
                mongo.datetime.datetime = mock.MagicMock('datetime')
                mongo.datetime.datetime.utcnow = mock.MagicMock(
                    return_value=UTCNOW)

                mongo.initialize_state(db, PLAYBOOK_ID, dynamic={})
                db['state'].insert.assert_called_once_with({
                    'failed': False,
                    'created': UTCNOW,
                    'completed_steps': [],
                    'dynamic': {},
                    'remaining_steps': [],
                    'group': group,
                    'ended': None,
                    'active_step': {},
                    'reply_to': None,
                    'playbook_id': PLAYBOOK_ID,
                    'skipped_steps': []
                })

    def test_initialize_state_with_error(self):
        """
        Make sure that if mongo errors out we are notified with the
        proper exception
        """
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.insert = mock.MagicMock(
            side_effect=pymongo.errors.PyMongoError('test error'))
        db.__getitem__.return_value = collection
        playbook = '555544443333222211110000'

        # We should get a PyMongoError
        self.assertRaises(
            pymongo.errors.PyMongoError, mongo.initialize_state, db, playbook)
