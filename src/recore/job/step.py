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
import recore.mongo
import recore.utils


def run(channel, project, id, params={}):
    props = pika.spec.BasicProperties()
    props.correlation_id = id
    out = logging.getLogger('recore')
    notify = logging.getLogger('recore.stdout')
    notify.info('About to kick off a worker task: <id>%s' % id)

    # TODO: Use the DB to look up step and required dynamic inputs
    # mongo_db = recore.mongo.database
    # step = recore.mongo....
    # dynamic = step...
    dynamic = {}
    params.update(dynamic)
    routing_key = 'plugin.shexec.start'

    to_worker = recore.utils.create_json_str({
        'project': project,
        'params': params})
    notify.info("Created string: %s" % to_worker)
    out.debug(
        "Sending message for project %s and correlation if %s "
        "to routing key %s: %s" % (project, id, routing_key, to_worker))
    try:
        channel.basic_publish(
            exchange='re',
            routing_key=routing_key,
            properties=props,
            body=to_worker)
        notify.info("Kicked off jorb")
        out.info("Kicked off job %s for project %s with correlation id %s" % (
            routing_key, project, id))
    except pika.exceptions.ChannelError, ce:
        out.error(
            "Unable to send message to start job: %s ... "
            "due to channel issue. Propagating Pika error: %s" % (
                to_worker, ce))
        raise ce
