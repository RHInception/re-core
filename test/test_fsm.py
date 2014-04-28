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

from . import TestCase, unittest


class TestMongo(TestCase):
    pass
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
