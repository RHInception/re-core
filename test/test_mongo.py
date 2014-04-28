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

    def test_lookup_project(self):
        """
        Make sure looking up projects follows the correct path
        """
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.find_one = mock.MagicMock(return_value={"data": "here"})
        db.__getitem__.return_value = collection

        # With result
        assert mongo.lookup_project(db, "project") == {"data": "here"}

        # No result
        collection.find_one = mock.MagicMock(return_value=None)
        assert mongo.lookup_project(db, "project") is None

        # Error result is {}
        assert mongo.lookup_project({}, "project") == {}


    def test_initialize_state(self):
        """
        Make sure that creating the initial state uses proper data
        """
        db = mock.MagicMock()
        collection = mock.MagicMock()
        collection.insert = mock.MagicMock(return_value=12345)
        db.__getitem__.return_value = collection
        project = 'testproject'

        with mock.patch('recore.mongo.lookup_project') as (
                mongo.lookup_project):
            mongo.lookup_project = mock.MagicMock()
            mongo.lookup_project.return_value.get.return_value = []

            with mock.patch('recore.mongo.datetime.datetime') as (
                    mongo.datetime.datetime):
                mongo.datetime.datetime = mock.MagicMock('datetime')
                mongo.datetime.datetime.utcnow = mock.MagicMock(
                    return_value=UTCNOW)

                mongo.initialize_state(db, project, dynamic={})
                db['state'].insert.assert_called_once_with({
                    'active_step': {},
                    'completed_steps': [],
                    'created': UTCNOW,
                    'dynamic': {},
                    'project': project,
                    'remaining_steps': [],
                    'reply_to': None,
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
        project = 'testproject'

        # We should get a PyMongoError
        self.assertRaises(
            pymongo.errors.PyMongoError, mongo.initialize_state, db, project)


    # def test_update_state(self):
    #     """
    #     Verify that update_state inserts the proper information
    #     """
    #     db = mock.MagicMock()
    #     collection = mock.MagicMock()
    #     collection.update = mock.MagicMock(mock.MagicMock(return_value=12345))
    #     db.__getitem__.return_value = collection
    #     objectid = bson.ObjectId()

    #     for state in ('completed', 'failed'):
    #         mongo.update_state(db, objectid, state)

    #         db['state'].update.assert_called_once_with(
    #             {'_id': objectid},
    #             {'$push': {'step_log': state}})
    #         db['state'].update.reset_mock()

    # def test_update_state_with_error(self):
    #     """
    #     Make sure that if mongo errors out while updating a state
    #     we are notified with the proper exception
    #     """
    #     db = mock.MagicMock()
    #     collection = mock.MagicMock()
    #     collection.update = mock.MagicMock(
    #         side_effect=pymongo.errors.PyMongoError('test error'))
    #     db.__getitem__.return_value = collection
    #     objectid = bson.ObjectId()

    #     # We should get a PyMongoError
    #     self.assertRaises(
    #         pymongo.errors.PyMongoError,
    #         mongo.update_state, db, objectid, 'completed')
