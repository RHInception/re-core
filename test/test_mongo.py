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

from recore import mongo


# Mocks
connection = mock.MagicMock('connection')
mongo.MongoClient = mock.MagicMock(
    mongo.MongoClient, return_value=connection)


class TestMongo(TestCase):

    def tearDown(self):
        """
        Reset mocks.
        """
        mongo.MongoClient.reset_mock()
        connection.reset_mock()

    def test_connect(self):
        """
        Verify mongo connections work as expected
        """
        print mongo
        user = "user"
        passwd = "password"
        host = "127.0.0.1"
        port = 1234
        db = "database"

        result = mongo.connect(host, port, user, passwd, db)

        mongo.MongoClient.assert_called_with("mongodb://%s:%s@%s:%s/%s" % (
            user, passwd, host, port, db))
        print result
        assert result[0] == connection
        assert result[1] == connection[db]

    def test_lookup_project(self):
        """
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
