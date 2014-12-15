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
import recore.contextfilter
import recore.fsm
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
        db['DATABASE'],
        db['SSL'])
    recore.mongo.connection = c
    recore.mongo.database = d


def connect(host, port, user, password, db, ssl):
    # First, escape the parameters
    out = logging.getLogger('recore')
    (n, p) = escape_credentials(user, password)
    connect_string = "mongodb://%s:%s@%s:%s/%s?ssl=%s" % (
        n, p, host, port, db, ssl)
    cs_clean = "mongodb://%s:******@%s:%s/%s?ssl=%s" % (
        n, host, port, db, ssl)
    out.info("Initializing mongo db connection with connect string: %s" %
             cs_clean)

    connection = MongoClient(connect_string)
    db = connection[db]
    return (connection, db)


def lookup_playbook(d, pbid):
    """Given a mongodb database, `d`, search the 'playbooks' collection
for a document with the given `pbid`. `search_result` is either a hash
or `None` if no matches were found.
    """
    out = logging.getLogger('recore.playbook.' + str(pbid))
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


def lookup_state(c_id, pbid):
    """`c_id` is a correlation ID corresponding to the ObjectID value in
MongoDB.

pbid - the playbook id used for logging purposes
    """
    # using the recore.mongo.database database, create a
    # pymongo.collection.Collection object pointing at the 'state'
    # collection
    states = database['state']
    out = logging.getLogger('recore.playbook.' + str(pbid))
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
    logname = 'recore.playbook.' + str(pbid)
    out = logging.getLogger(logname)
    filter = recore.contextfilter.get_logger_filter(logname)

    # Look up the to-release playbook
    _playbook = lookup_playbook(d, pbid)

    # Insert triggers
    _playbook['execution'] = insert_step_triggers(_playbook['execution'], recore.fsm.TRIGGERS)

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
        'user_id': filter.get_field('user_id'),
        'playbook_id': pbid,
        'dynamic': dynamic,
        'execution': _playbook['execution'],
        'executed': [],
        'active_sequence': _active_sequence
    })

    try:
        id = d['state'].insert(state0)
        filter.set_field('deployment_id', str(id))
        out.debug("Added new state record with id: %s" % str(id))
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


def insert_step_triggers(execution, triggers=[]):
    """Insert the step triggers into the execution sequences

`triggers` - list of step triggers
`execution` - an execution sequence"""
    for sequence in execution:
        # Insert triggers into each execution sequence
        for t in triggers:
            _t = Trigger(t)
            # Record each index where a trigger needs to be
            # inserted. Begin by scanning all steps in this sequence
            insertions = []
            for i in xrange(len(sequence['steps'])):
                step = Step(sequence['steps'][i])
                # Do the needful for each 'NEXT_COMMAND'
                condition = t['WHEN']['NEXT_COMMAND']

                if step.command == condition:
                    insertions.append(i)

            # Inserting into a list will increment the index of all
            # later insertions by 1 * num_insertions. Record number of
            # insertions so we can add that to the index later
            increment = 0
            for insert in insertions:
                sequence['steps'].insert(insert + increment, _t.to_step())
                increment += 1

    return execution


class Step(object):
    def __init__(self, step):
        self._step = step

        if type(step) == str or \
           type(step) == unicode:
            # self.app_logger.debug("Next step is a string. Split it and route it")
            (command, sep, subcommand) = step.partition(':')
            parameters = {}
        else:
            # It's a dictionary - may have notify/parameters/
            # self.app_logger.debug("Next step has parameters to parse: %s" % step)
            _step_key = step.keys()[0]
            (command, sep, subcommand) = _step_key.partition(':')

        self._step_name = "{CMD}:{SUB}".format(CMD=command, SUB=subcommand)
        self._command = command
        self._subcommand = subcommand

    @property
    def step_name(self):
        """Return name of this step"""
        return self._step_name

    @property
    def command(self):
        """Return command of this step"""
        return self._command

    @property
    def subcommand(self):
        """Return subcommand of this step"""
        return self._subcommand

    def __str__(self):
        return self.step_name


class Trigger(Step):
    def __init__(self, *args, **kwargs):
        super(Trigger, self).__init__(*args, **kwargs)
        self._command = self._step['COMMAND']
        self._subcommand = self._step['SUBCOMMAND']
        self._step_name = "{CMD}:{SUB}".format(CMD=self._command, SUB=self._subcommand)

    def to_step(self):
        return {
            self.step_name: self._step['PARAMETERS']
        }

    # def __repr__(self):
    #     return str(self.to_step())
