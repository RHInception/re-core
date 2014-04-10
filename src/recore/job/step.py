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

import pika.spec
import logging
import recore.utils

def run(channel, project, id):
    props = pika.spec.BasicProperties()
    props.correlation_id = id
    out = logging.getLogger('recore.stdout')
    out.info('About to kick off a worker task: <id>%s' % id)

    to = {'project': project}
    to_worker = recore.utils.create_json_str(to)

    channel.basic_publish(exchange='re',
                          routing_key='plugin.shexec.start',
                          properties=props,
                          body=to_worker)
