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
import urllib
import datetime

connection = None
database = None

def connect(host, port, user, password, db):
    # First, escape the parameters
    (n, p) = escape_credentials(user, password)
    connect_string = "mongodb://%s:%s@%s:%s/%s" % \
                     (n, p, host, port, db)
    connection = MongoClient(connect_string)
    db = connection[db]
    return (connection, db)

def lookup_project(d, project):
    """Given a mongodb database, `d`, search the 'projects' collection for
any documents which match the `project` key provided."""
    projects = d['projects']
    search_result = projects.find_one({'project': project})
    return search_result

def lookup_state(d, c_id):
    """`d` is a mongodb database and `c_id` is a correlation ID."""
    pass

def initialize_state(d, project):
    """Initialize the state of a given project release"""
    # Just record the name now and insert an empty array to record the
    # result of steps. Oh, and when it started. Maybe we'll even add
    # who started it later!
    state0 = {
        'project': project,
        'step_log': [],
        'started': datetime.datetime.utcnow()
    }
    id = d['state'].insert(state0)
    return id

def update_state(d, **kwargs):
    """`d` is a mongodb database and `**kwargs` is undefined at this
time. sorry"""
    pass

def escape_credentials(n, p):
    """Return the RFC 2396 escaped version of name `n` and password `p` in
a 2-tuple"""
    return (urllib.quote(n), urllib.quote(p))
