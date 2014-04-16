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
import sys

def start_logging(log_file, log_level):
    # First the file logging
    output = logging.getLogger('recore')
    output.setLevel(logging.getLevelName(log_level))
    log_handler = logging.FileHandler(log_file)
    log_handler.setLevel(logging.getLevelName(log_level))
    log_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(module)s - %(levelname)s - %(message)s'))
    output.addHandler(log_handler)
    output.debug("initialized logger")

    # And now the stdout logging
    out2 = logging.getLogger('recore.stdout')
    out2.setLevel('DEBUG')
    lh2 = logging.StreamHandler(stream=sys.stdout)
    lh2.setFormatter(logging.Formatter(
        '%(module)s - %(levelname)s - %(message)s'))
    out2.addHandler(lh2)
    out2.debug("initialized stdout logger")

def parse_config(config_path):
    """Read in the config file. Or die trying"""
    try:
        config = recore.utils.parse_config_file(config_path)
        start_logging(config.get('LOGFILE', 'recore.log'), config.get('LOGLEVEL', 'INFO'))
        notify = logging.getLogger('recore.stdout')
        notify.debug('Parsed configuration file')
    except IOError:
        print "ERROR config doesn't exist"
        raise SystemExit(1)
    except ValueError, vex:
        print "ERROR config file is not valid json: %s" % vex
        raise SystemExit(1)
    return config

def init_mongo(db):
    """Open up a MongoDB connection"""
    (c, d) = recore.mongo.connect(
        db['SERVERS'][0],
        db['PORT'],
        db['NAME'],
        db['PASSWORD'],
        db['DATABASE'])
    recore.mongo.connection = c
    recore.mongo.database = d

 

def init_amqp(mq):
    """Open a channel to our AMQP server"""
    import pika.exceptions

    out = logging.getLogger('recore')
    notify = logging.getLogger('recore.stdout')

    (channel, connection) = recore.utils.connect_mq(
        name=mq['NAME'],
        password=mq['PASSWORD'],
        server=mq['SERVER'],
        exchange=mq['EXCHANGE'])
    connect_string = "amqp://%s:******@%s:%s/%s" % \
                 (mq['NAME'], mq['SERVER'], mq['PORT'], mq['EXCHANGE'])
    out.debug("Opened AMQP connection: %s" % connect_string)

    receive_as = mq['QUEUE']
    result = channel.queue_declare(durable=True, queue=receive_as)
    queue_name = result.method.queue
    return (channel, connection, queue_name)


def watch_the_queue(channel, connection, queue_name):
    """Begin consuming messages from the bus. Set our default callback
handler"""
    channel.basic_consume(recore.receive.receive,
                          queue=queue_name,
                          no_ack=True)
    try:
        notify = logging.getLogger('recore.stdout')
        notify.info('FSM online and listening for messages')
        channel.start_consuming()
        out = logging.getLogger('recore')
        out.debug('Consuming messages from queue: %s' % queue_name)
    except KeyboardInterrupt:
        channel.close()
        connection.close()
        pass

def main(args):
    import pymongo.errors

    config = parse_config(args.config)

    out = logging.getLogger('recore')
    notify = logging.getLogger('recore.stdout')
    try:
        init_mongo(config['DB'])
    except pymongo.errors.ConnectionFailure, cfe:
        out.fatal("Connection failiure to Mongo: %s. Exiting ..." % cfe)
        notify.fatal("Connection failiure to Mongo: %s. Exiting ..." % cfe)
        raise SystemExit(1)
    except pymongo.errors.PyMongoError:
        out.fatal("Unknown failiure with Mongo: %s. Exiting ..." % cfe)
        notify.fatal("Unknown failiure with Mongo: %s. Exiting ..." % cfe)
        raise SystemExit(1)

    try:
        (channel, connection, queue_name) = init_amqp(config['MQ'])
    except KeyError, ke:
        out.fatal("Missing a required key in MQ config: %s" % ke)
        notify.fatal("Missing a required key in MQ config: %s" % ke)
        raise SystemExit(1)
    except pika.exceptions.ProbableAuthenticationError, paex:
        out.fatal("Authentication issue connecting to AMQP: %s" % paex)
        notify.fatal("Authentication issue connecting to AMQP: %s" % paex)
        raise SystemExit(1)
    except (
            pika.exceptions.ProtocolSyntaxError,
            pika.exceptions.AMQPError), ex:
        out.fatal("Unknown issue connecting to AMQP: %s" % ex)
        notify.fatal("Unknown issue connecting to AMQP: %s" % ex)
        raise SystemExit(1)
    try:
        watch_the_queue(channel, connection, queue_name)
    except (
            pika.exceptions.ProtocolSyntaxError,
            pika.exceptions.AMQPError), ex:
        out.fatal("Unknown issue watching the queue: %s" % ex)
        notify.fatal("Unknown issue watching the queue: %s" % ex)
        raise SystemExit(1)

    out.info('FSM fully initialized')
    notify.info('FSM fully initialized')

######################################################################
# pika spews messages about logging handlers by default. So we're just
# going to set the level to CRITICAL so we don't see most of them.
logging.getLogger('pika').setLevel(logging.DEBUG)
