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

    # Of the attributes carried by the properties object we are
    # primarily interested in the following:
    #
    # - `app_id` - Name of the plugin
    # - `correlation_id` - ID of the release this job was ran for

    correlation_id = properties.correlation_id
    message['timestamp'] = dt.utcnow()
    # Not sending 'app_id' while testing
    #message['plugin'] = properties.app_id
    message['plugin'] = 'shexec'

    recore.mongo.update_state(recore.mongo.database,
                              correlation_id,
                              message)
