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

"""
This is where we create new jobs

FSM will get {"project": "$NAME"} with the topic of job.create and a reply_to set

it expects a message with {"id": $an_int_here} back to the reply_to.
"""

import recore.utils
import recore.mongo
import logging

def release(ch, project, reply_to):
    """`ch` is an open AMQP channel

    `project` is the name of a project to begin a release for.

    `reply_to` is a temporary channel

Reference the project name against the database to retrieve a list of
release steps to execute.

For now we're just going to pretend we did that part.

We then generate a correlation_id by inserting a new document into the
'state' collection. The correlation_id is equivalent to the
automatically generated '_id' property of this document.

In the future that ID will be passed to the workers. For now we will
just return it.
    """
    out = logging.getLogger('recore.stdout')
    out.info("new job submitted from rest for %s. Need to look it up first in mongo" % project)
    mongo_db = recore.mongo.database
    project_exists = recore.mongo.lookup_project(mongo_db, project)

    out.info("looked up project: %s" % project)

    if project_exists:
        id = str(recore.mongo.initialize_state(mongo_db, project))
    else:
        id = None

    body = {'id': str(id)}
    ch.basic_publish(exchange='',
                     routing_key=reply_to,
                     body=recore.utils.create_json_str(body))
    out = logging.getLogger('recore.stdout')
    out.info('Emitted message to start new release for %s. Job id: %s' %
             (project, str(id)))

    return id
