# -*- coding: utf-8 -*-
# Copyright © 2014 SEE AUTHORS FILE
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

from pymongo import MongoClient
from bson.objectid import ObjectId
import pymongo.errors
import pymongo.database
import urllib
import datetime
import logging
import recore.constants
import recore.utils

connection = None
database = None


def init_mongo(db):
    """Open up a MongoDB connection"""
    import recore.mongo
    (c, d) = connect(
        db['SERVERS'][0],
        db['PORT'],
        db['NAME'],
        db['PASSWORD'],
        db['DATABASE'])
    recore.mongo.connection = c
    recore.mongo.database = d


def connect(host, port, user, password, db):
    # First, escape the parameters
    (n, p) = escape_credentials(user, password)
    connect_string = "mongodb://%s:%s@%s:%s/%s" % (
        n, p, host, port, db)
    cs_clean = "mongodb://%s:******@%s:%s/%s" % (
        n, host, port, db)
    out = logging.getLogger('recore')
    connection = MongoClient(connect_string)
    db = connection[db]
    out.debug("Opened: %s" % cs_clean)
    out.info("Connection to the database succeeded")
    return (connection, db)


def lookup_playbook(d, pbid):
    """Given a mongodb database, `d`, search the 'playbooks' collection
for a document with the given `pbid`. `search_result` is either a hash
or `None` if no matches were found.
    """
    out = logging.getLogger('recore')
    try:
        # TODO: make this a config var
        groups = d['playbooks']
        filter = {
            '_id': ObjectId(str(pbid))
        }
        search_result = groups.find_one(filter)

        if search_result:
            out.debug("Found playbook definition: %s" % pbid)
        else:
            out.debug("No result found for playbook: %s" % pbid)
        return search_result
    except KeyError, kex:
        out.error(
            "KeyError raised while trying to look up a playbook: %s."
            "Returning {}" % kex)
        return {}


def lookup_state(c_id):
    """`c_id` is a correlation ID corresponding to the ObjectID value in
MongoDB.
    """
    # using the recore.mongo.database database, create a
    # pymongo.collection.Collection object pointing at the 'state'
    # collection
    states = database['state']
    out = logging.getLogger('recore.stdout')
    out.debug("Looking up state for %s" % ObjectId(str(c_id)))
    # findOne state document with _id of `c_id`. If a document is
    # found, returns a hash, if no document is found, returns None
    project_state = states.find_one({'_id': ObjectId(str(c_id))})
    # After adding tests, don't bother assigning project_state, just
    # return it.
    return project_state


def initialize_state(d, playbook, dynamic={}):
    """Initialize the state of a given project release"""
    # Just record the name now and insert an empty array to record the
    # result of steps. Oh, and when it started. Maybe we'll even add
    # who started it later!
    #
    # We expect this to return an ObjectID object. We don't care so
    # much about what we're `insert`ing into the state collection. `d`
    # would be a Mongo database object, but we can't unittest with a
    # real one, so we need mock one up, give a string for the project
    # name, and make sure the insert method returns a mocked ObjectID
    # which when `str`'d returns a reasonable value.
    out = logging.getLogger('recore')

    _playbook = lookup_playbook(d, playbook)
    project_steps = _playbook.get('execution', [])

    # TODO: Validate dynamic before inserting state ...
    state0 = recore.constants.NEW_STATE_RECORD.copy()
    state0.update({
        'created': datetime.datetime.utcnow(),
        'group': _playbook['group'],
        'dynamic': dynamic,
        'remaining_steps': project_steps,
        'playbook_id': playbook
    })

    try:
        id = d['state'].insert(state0)
        out.info("Added new state record with id: %s" % str(id))
        out.debug("New state record: %s" % state0)
    except pymongo.errors.PyMongoError, pmex:
        out.error(
            "Unable to save new state record %s. "
            "Propagating PyMongo error: %s" % (state0, pmex))
        raise pmex
    return id


def escape_credentials(n, p):
    """Return the RFC 2396 escaped version of name `n` and password `p` in
a 2-tuple"""
    return (urllib.quote(n), urllib.quote(p))
