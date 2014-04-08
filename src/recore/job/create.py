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

def release(ch, project, reply_to):
    """
    `ch` is an open AMQP channel
    `project` is the name of a project to begin a release for.

When we aren't just doing this for fakesies we'll reference that name
against the database to retrieve a list of release steps to execute.

For now we're just going to pretend we did that part.

We then generate a correlation_id. In the future that will be passed
to the workers. For now we will just return it."""
    # TODO: Don't generate fake correlation IDs like this. Idea: use
    # one of the ID parameters in MongoDB.
    import time

    body = {'id': abs(int(hash(time.time())))}

    ch.basic_publish(exchange='',
                     routing_key=reply_to,
                     body=recore.utils.create_json_str(body))
