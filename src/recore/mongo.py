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


def initialize_state(d, pbid, dynamic={}):
    """Initialize the state of a given project release

#. Lookup the playbook
#. Prep the: active sequence, fill in 'completed_steps' with []
#. Copy the template state record
#. Expand sequences
#. Update the record with items specific to this playbook
#. Insert the new state record
#. Return the ID"""

    out = logging.getLogger('recore')

    # Look up the to-release playbook
    _playbook = lookup_playbook(d, pbid)

    # Expand sequences = duplicate sequences for each host in the
    # sequence. Set hosts to just that one host.
    _playbook['execution'] = expand_sequences(_playbook['execution'])
    # Pop off the first execution sequence from the playbook
    # 'execution' item. Set it as the active sequence.
    _active_sequence = _playbook['execution'].pop(0)
    # Prime the active sequence to accept completed steps
    _active_sequence['completed_steps'] = []

    # TODO: Validate dynamic before inserting state ...
    state0 = recore.constants.NEW_STATE_RECORD.copy()
    state0.update({
        'created': datetime.datetime.utcnow(),
        'group': _playbook['group'],
        'playbook_id': pbid,
        'dynamic': dynamic,
        'execution': _playbook['execution'],
        'executed': [],
        'active_sequence': _active_sequence
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


def expand_sequences(execution):
    """For each SEQUENCE in EXECUTION SEQUENCES, For each HOST in
    SEQUENCE, duplicate the SEQUENCE, and then set the 'hosts' key
    to HOST.

    E.g., Given a playbook with one execution sequence, with 2
    hosts defined, foo.com and bar.com, the result is: two
    execution sequences, one with hosts = foo.com, one with
    hosts=bar.com.

    Parameters:
    #. 'execution' - A list of execution sequences

    Returns: the new (expanded) sequences as a list
    """
    expanded_sequences = []
    original_sequences = execution
    for sequence in original_sequences:
        # Loop over each sequence
        for host in sequence['hosts']:
            # Loop over each host in this sequence
            _new_sequence = sequence.copy()
            _new_sequence['hosts'] = [host]
            expanded_sequences.append(_new_sequence)
    return expanded_sequences
