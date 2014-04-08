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

import recore.utils
import recore.receive
import logging
import recore.mongo

def main(args):
    try:
        config = recore.utils.parse_config_file(args.config)
    except IOError:
        print "ERROR config doesn't exist"
        sys.exit(1)

    ##################################################################
    # Set up the mongodb hotness.
    db = config['DB']
    (c, d) = recore.mongo.connect(db['SERVERS'][0],
                                  db['PORT'],
                                  db['NAME'],
                                  db['PASSWORD'],
                                  db['DATABASE'])

    recore.mongo.connection = c
    recore.mongo.database = d

    ##################################################################
    # Gimme dat AMQP bay-bee
    (channel, connection) = recore.utils.connect_mq(
        name=config['MQ']['NAME'],
        password=config['MQ']['PASSWORD'],
        server=config['MQ']['SERVER'],
        exchange=config['MQ']['EXCHANGE'])

    receive_as = config['MQ']['QUEUE']
    print "Receiving as component: %s\n" % receive_as
    result = channel.queue_declare(durable=True, queue=receive_as)
    queue_name = result.method.queue
    channel.basic_consume(recore.receive.receive,
                          queue=queue_name,
                          no_ack=True)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.close()
        connection.close()
        pass

######################################################################
# pika spews messages about logging handlers by default. So we're just
# going to set the level to CRITICAL so we don't see most of them.
logging.getLogger('pika').setLevel(logging.CRITICAL)
