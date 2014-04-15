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
Update job status
"""

import logging
import recore.mongo
import recore.utils
from datetime import datetime as dt

def update(ch, method, properties, message):
    """
    - `ch` - An open channel object
    - `method` - AMQP method object
    - `properties` - Job response message properties
    - `message` - Datastructure describing the new state
    """
    out = logging.getLogger('recore')
    notify = logging.getLogger('recore.stdout')
    notify.info("Lets update this status")
    # Of the attributes carried by the properties object we are
    # primarily interested in the following:
    #
    # - `app_id` - Name of the plugin
    # - `correlation_id` - ID of the release this job was ran for
    correlation_id = properties.correlation_id
    out.info("Updating mongodb with latest message for correlation id %s" % (
        correlation_id))
    notify.info("id: %s" % correlation_id)
    message['timestamp'] = dt.utcnow()
    # Not sending 'app_id' while testing
    #message['plugin'] = properties.app_id
    message['plugin'] = 'shexec'

    out.debug("Storing the following in mongodb for correlation %s: %s" % (
        correlation_id, message))
    recore.mongo.update_state(recore.mongo.database,
                              correlation_id,
                              message)


def running(properties, running):
    """
    - `properties` - Job response message properties
    - `running` - Boolean noting if the release is running
    """
    out = logging.getLogger('recore')
    notify = logging.getLogger('recore.stdout')

    correlation_id = properties.correlation_id
    notify.info("Updating the running status for correlation if %s" % (
        correlation_id))
    out.info("Setting release running status for correlation id %s to %s" % (
        correlation_id, running))
    recore.mongo.mark_release_running(recore.mongo.database, correlation_id, running)
