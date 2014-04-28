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
import json
import pika
import recore.fsm
import threading


MQ_CONF = {}
connection = None
out = logging.getLogger('recore.amqp')


def init_amqp(mq):
    """Open a channel to our AMQP server"""
    import recore.amqp
    recore.amqp.MQ_CONF = mq

    creds = pika.credentials.PlainCredentials(mq['NAME'], mq['PASSWORD'])
    params = pika.ConnectionParameters(
        host=str(mq['SERVER']),
        credentials=creds)
    out.debug('Attemtping to open channel...')
    connect_string = "amqp://%s:******@%s:%s/%s" % (
        mq['NAME'], mq['SERVER'], mq['PORT'], mq['EXCHANGE'])
    recore.amqp.connection = pika.SelectConnection(parameters=params,
                                                   on_open_callback=on_open)
    return recore.amqp.connection

def on_open(connection):
    """
    Call back when a connection is opened.
    """
    out.debug("Opened AMQP connection")
    connection.channel(on_channel_open)


def on_channel_open(channel):
    """
    Call back when a channel is opened.
    """
    out.debug("MQ channel opened. Declaring exchange ...")
    channel.exchange_declare(exchange=MQ_CONF['EXCHANGE'],
                             durable=True,
                             exchange_type='topic')
    consumer_tag = channel.basic_consume(
        receive,
        queue=MQ_CONF['QUEUE'])


# def watch_the_queue(channel, connection, queue_name):
#     """Begin consuming messages `queue_name` on the bus. Set our default
# callback handler
#     """
#     channel.basic_consume(receive,
#                           queue=queue_name)
#     try:
#         notify = logging.getLogger('recore.stdout')
#         notify.info('FSM online and listening for messages')
#         out = logging.getLogger('recore')
#         out.debug('Consuming messages from queue: %s' % queue_name)
#     except KeyboardInterrupt:
#         channel.close()
#         connection.close()
#         pass

def receive(ch, method, properties, body):
    """
    Callback for watching the FSM queue
    """
    out = logging.getLogger('recore')
    notify = logging.getLogger('recore.stdout')
    msg = json.loads(body)
    topic = method.routing_key
    out.debug("Message: %s" % msg)
    ch.basic_ack(delivery_tag=method.delivery_tag)

    if topic == 'job.create':
        id = None
        try:
            # We need to get the name of the temporary
            # queue to respond back on.
            notify.info("new job create for: %s" % msg['project'])
            out.info(
                "New job requested, starting release "
                "process for %s ..." % msg["project"])
            notify.debug("Job message: %s" % msg)
            reply_to = properties.reply_to

            id = recore.job.create.release(
                ch, msg['project'], reply_to, msg['dynamic'])
        except KeyError, ke:
            notify.info("Missing an expected key in message: %s" % ke)
            out.error("Missing an expected key in message: %s" % ke)
            return

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
