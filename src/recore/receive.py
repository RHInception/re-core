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

import logging
import recore.utils
import recore.fsm
import recore.job.create
import recore.job.step
import recore.job.status


def receive(ch, method, properties, body):
    out = logging.getLogger('recore')
    notify = logging.getLogger('recore.stdout')
    msg = recore.utils.load_json_str(body)
    topic = method.routing_key
    out.info('Received a new message via routing key %s' % topic)
    out.debug("Message: %s" % msg)

    ch.basic_ack(delivery_tag=method.delivery_tag)

    ##################################################################
    # NEW JOB
    #
    # FSM will get {"project": "$NAME"} with the topic of job.create
    # and a reply_to set
    #
    # FSM sends a msg with {"id": MongoObjectID} back to the
    # reply_to. This ObjectID is the same as the value of the _id
    # property of the new document created in the 'state' collection.
    ##################################################################
    if topic == 'job.create':
        id = None
        try:
            # We need to get the name of the temporary
            # queue to respond back on.
            notify.info("new job create for: %s" % msg['project'])
            notify.info("Job message: %s" % msg)
            reply_to = properties.reply_to

            out.info(
                "New job requested, starting release "
                "process for %s ..." % msg["project"])

            id = recore.job.create.release(
                ch, msg['project'], reply_to, msg['dynamic'])
        except KeyError, ke:
            notify.info("Missing an expected key in message: %s" % ke)
            out.error("Missing an expected key in message: %s" % ke)

        if id:
            # Skip this try/except until we work all the bugs out of the FSM
            # try:
            runner = recore.fsm.FSM(id)
            runner.start()
            while runner.isAlive():
                runner.join(0.3)
            # except Exception, e:
            # notify.error(str(e))

    else:
        out.warn("Unknown routing key %s. Doing nothing ...")
        notify.info("IDK what this is: %s" % topic)

    notify.info("end receive() routine")
    out.debug("end receive() routine")
