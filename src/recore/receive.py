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

import pdb
import recore.utils
import recore.job.create
import recore.job.step
import recore.job.status

def receive(ch, method, properties, body):
    # print "devops Topic: %s\nMessage: %s\n" % (method.routing_key, body,)
    #ch.basic_ack(properties.delivery_tag)
    # print "acked it"
    msg = recore.utils.load_json_str(body)
    # print "message plz: %s" % msg
    topic = method.routing_key
    # print "routed: %s" % str(topic)
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
        # We need to get the name of the temporary queue to respond back on.
        print "new job create"
        reply_to = properties.reply_to
        # print "reply to happened? %s" % reply_to
        id = recore.job.create.release(ch, msg['project'], reply_to)
        # print "got that id"
        recore.job.step.run(ch, msg['project'], id)
        print "foo"
    elif topic == 'release.step':
        # Handles updates from the workers running jobs
        print "Got a releaes step update"
        try:
            recore.job.status.update(ch, method, properties, msg)
            # If the response was fail we need to halt the release
            if msg['status'] == 'failed':
                # TODO: use a logger
                print "Job JOB_NAME_HERE for release ID_HERE failed. Aborting release."
                # The release is no longer running
                recore.job.status.running(properties, False)
            if msg['status'] == 'completed':
                # TODO: use a logger
                print "Job JOG_NAME_HERE compleated for release ID_HERE. Executing next step."
                # if there are no more steps mark running as false
                #recore.job.status.running(properties, False)
                # TODO: execute the next step
                pass
        except Exception, e:
            print e
        print "We finished processing the update"
    else:
        print "IDK what this is"
        # TODO: This is a glorified case/switch statement. There needs
        # to be a better way to map topics to functions. Consider
        # refactoring (later, lol) to a Python module-tree that
        # mimicks the topic hierarchy. Then just pass some
        # intelligently named function everything we know?
        print topic
    print "end receive() routine"
