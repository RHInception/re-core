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
import time
import pika
import recore.fsm
import recore.job.create
import signal


MQ_CONF = {}
CONF = {}
out = logging.getLogger('recore.amqp')

# Special Pika reconnection logging setup. Ripped from
# https://pika.readthedocs.org/en/0.9.14/examples/asynchronous_consumer_example.html
LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


class WinternewtBusClient(object):  # pragma: no cover
    """This is an example consumer that will handle unexpected interactions
    with RabbitMQ such as channel and connection closures.

    If RabbitMQ closes the connection, it will reopen it. You should
    look at the output, as there are limited reasons why the connection may
    be closed, which usually are tied to permission related issues or
    socket timeouts.

    If the channel is closed, it will indicate a problem with one of the
    commands that were issued and that should surface in the output as well.

    """

    def __init__(self, config):
        """Create a new instance of the consumer class, passing in the AMQP
        URL used to connect to RabbitMQ.

        :param str amqp_url: The AMQP url to connect with

        """
        c = config['MQ']
        self.EXCHANGE = c['EXCHANGE']
        self.EXCHANGE_TYPE = 'topic'
        self.QUEUE = c['QUEUE']
        self.ROUTING_KEY = 'job.create'
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._creds = pika.credentials.PlainCredentials(
            c['NAME'], c['PASSWORD'])
        self._params = pika.ConnectionParameters(
            host=str(c['SERVER']), credentials=self._creds)
        self.c = c

    def connect(self):
        """This method connects to RabbitMQ, returning the connection handle.
        When the connection is established, the on_connection_open method
        will be invoked by pika.

        :rtype: pika.SelectConnection

        """
        connect_string = "amqp://%s:******@%s:%s/%s" % (
            self.c['NAME'], self.c['SERVER'],
            self.c['PORT'], self.c['EXCHANGE'])
        out.debug('Attempting to open channel with connect string: %s' % (
            connect_string))

        try:
            return pika.SelectConnection(
                parameters=self._params,
                on_open_callback=self.on_connection_open,
                stop_ioloop_on_close=False)
        except pika.exceptions.AMQPConnectionError, ae:
            # This means we couldn't connect, so act like a reconnect
            out.warn('Unable to make connection: %s' % ae.message)
            self.on_connection_closed(None, -1, str(ae))

    def close_connection(self):
        """This method closes the connection to RabbitMQ."""
        LOGGER.info('Closing connection')
        self._connection.close()

    def add_on_connection_close_callback(self):
        """This method adds an on close callback that will be invoked by pika
        when RabbitMQ closes the connection to the publisher unexpectedly.

        """
        LOGGER.info('Adding connection close callback')
        self._connection.add_on_close_callback(self.on_connection_closed)

    def on_connection_closed(self, connection, reply_code, reply_text):
        """This method is invoked by pika when the connection to RabbitMQ is
        closed unexpectedly. Since it is unexpected, we will reconnect to
        RabbitMQ if it disconnects.

        :param pika.connection.Connection connection: The closed connection obj
        :param int reply_code: The server provided reply_code if given
        :param str reply_text: The server provided reply_text if given

        """
        self._channel = None
        if self._closing:
            self._connection.ioloop.stop()
        else:
            LOGGER.warning('Connection closed, reopening in 5 seconds: (%s) %s',
                           reply_code, reply_text)
            time.sleep(5)
            self.reconnect()

    def on_connection_open(self, unused_connection):
        """This method is called by pika once the connection to RabbitMQ has
        been established. It passes the handle to the connection object in
        case we need it, but in this case, we'll just mark it unused.

        :type unused_connection: pika.SelectConnection

        """
        LOGGER.info('Connection opened')
        self.add_on_connection_close_callback()
        self.open_channel()

    def reconnect(self):
        """Will be invoked by the IOLoop timer if the connection is
        closed. See the on_connection_closed method.

        """
        if getattr(self, '_connection', None):
            # This is the old connection IOLoop instance, stop its ioloop
            self._connection.ioloop.stop()

        if not self._closing:

            # Create a new connection
            self._connection = self.connect()

            # There is now a new connection, needs a new ioloop to run
            self._connection.ioloop.start()

    def add_on_channel_close_callback(self):
        """This method tells pika to call the on_channel_closed method if
        RabbitMQ unexpectedly closes the channel.

        """
        LOGGER.info('Adding channel close callback')
        self._channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, reply_code, reply_text):
        """Invoked by pika when RabbitMQ unexpectedly closes the channel.
        Channels are usually closed if you attempt to do something that
        violates the protocol, such as re-declare an exchange or queue with
        different parameters. In this case, we'll close the connection
        to shutdown the object.

        :param pika.channel.Channel: The closed channel
        :param int reply_code: The numeric reason the channel was closed
        :param str reply_text: The text reason the channel was closed

        """
        LOGGER.warning('Channel %i was closed: (%s) %s',
                       channel, reply_code, reply_text)
        self._connection.close()

    def on_channel_open(self, channel):
        """This method is invoked by pika when the channel has been opened.
        The channel object is passed in so we can make use of it.

        Since the channel is now open, we'll declare the exchange to use.

        :param pika.channel.Channel channel: The channel object

        """
        LOGGER.info('Channel opened')
        self._channel = channel
        self.add_on_channel_close_callback()
        self.setup_exchange(self.EXCHANGE)

    def setup_exchange(self, exchange_name):
        """Setup the exchange on RabbitMQ.

        :param str|unicode exchange_name: The name of the exchange

        """
        LOGGER.info('Exchange details: name: {name}, type: {type}, durability: {durability}'.format(
            name=exchange_name, type=self.EXCHANGE_TYPE, durability=True))
        self.setup_queue(self.QUEUE)

    def setup_queue(self, queue_name):
        """Setup the queue on RabbitMQ.

        :param str|unicode queue_name: The name of the queue

        """
        LOGGER.info('Queue details: name: {name}, durability: {durability}'.format(
            name=queue_name, durability=True))

        self.start_consuming()

    def add_on_cancel_callback(self):
        """Add a callback that will be invoked if RabbitMQ cancels the consumer
        for some reason. If RabbitMQ does cancel the consumer,
        on_consumer_cancelled will be invoked by pika.

        """
        LOGGER.info('Adding consumer cancellation callback')
        self._channel.add_on_cancel_callback(self.on_consumer_cancelled)

    def on_consumer_cancelled(self, method_frame):
        """Invoked by pika when RabbitMQ sends a Basic.Cancel for a consumer
        receiving messages.

        :param pika.frame.Method method_frame: The Basic.Cancel frame

        """
        LOGGER.info('Consumer was cancelled remotely, shutting down: %r',
                    method_frame)
        if self._channel:
            self._channel.close()

    def acknowledge_message(self, delivery_tag):
        """Acknowledge the message delivery from RabbitMQ by sending a
        Basic.Ack RPC method for the delivery tag.

        :param int delivery_tag: The delivery tag from the Basic.Deliver frame

        """
        LOGGER.info('Acknowledging message %s', delivery_tag)
        self._channel.basic_ack(delivery_tag)

    def on_message(self, unused_channel, basic_deliver, properties, body):
        """Invoked by pika when a message is delivered from RabbitMQ. The
        channel is passed for your convenience. The basic_deliver object that
        is passed in carries the exchange, routing key, delivery tag and
        a redelivered flag for the message. The properties passed in is an
        instance of BasicProperties with the message properties and the body
        is the message that was sent.

        :param pika.channel.Channel unused_channel: The channel object
        :param pika.Spec.Basic.Deliver: basic_deliver method
        :param pika.Spec.BasicProperties: properties
        :param str|unicode body: The message body

        """
        LOGGER.info('Received message # %s from %s: %s',
                    basic_deliver.delivery_tag, properties.app_id, body)
        self.acknowledge_message(basic_deliver.delivery_tag)
        receive(unused_channel, basic_deliver, properties, body)

    def on_cancelok(self, unused_frame):
        """This method is invoked by pika when RabbitMQ acknowledges the
        cancellation of a consumer. At this point we will close the channel.
        This will invoke the on_channel_closed method once the channel has been
        closed, which will in-turn close the connection.

        :param pika.frame.Method unused_frame: The Basic.CancelOk frame

        """
        LOGGER.info('RabbitMQ acknowledged the cancellation of the consumer')
        self.close_channel()

    def stop_consuming(self):
        """Tell RabbitMQ that you would like to stop consuming by sending the
        Basic.Cancel RPC command.

        """
        if self._channel:
            LOGGER.info('Sending a Basic.Cancel RPC command to RabbitMQ')
            self._channel.basic_cancel(self.on_cancelok, self._consumer_tag)

    def start_consuming(self):
        """This method sets up the consumer by first calling
        add_on_cancel_callback so that the object is notified if RabbitMQ
        cancels the consumer. It then issues the Basic.Consume RPC command
        which returns the consumer tag that is used to uniquely identify the
        consumer with RabbitMQ. We keep the value to use it when we want to
        cancel consuming. The on_message method is passed in as a callback pika
        will invoke when a message is fully received.

        """
        LOGGER.info('Issuing consumer related RPC commands')
        self.add_on_cancel_callback()
        self._consumer_tag = self._channel.basic_consume(self.on_message,
                                                         self.QUEUE)

    def close_channel(self):
        """Call to close the channel with RabbitMQ cleanly by issuing the
        Channel.Close RPC command.

        """
        LOGGER.info('Closing the channel')
        self._channel.close()

    def open_channel(self):
        """Open a new channel with RabbitMQ by issuing the Channel.Open RPC
        command. When RabbitMQ responds that the channel is open, the
        on_channel_open callback will be invoked by pika.

        """
        LOGGER.info('Creating a new channel')
        self._connection.channel(on_open_callback=self.on_channel_open)

    def run(self):
        """Run the example consumer by connecting to RabbitMQ and then
        starting the IOLoop to block and allow the SelectConnection to operate.

        """
        self._connection = self.connect()
        self._connection.ioloop.start()

    def stop(self):
        """Cleanly shutdown the connection to RabbitMQ by stopping the consumer
        with RabbitMQ. When RabbitMQ confirms the cancellation, on_cancelok
        will be invoked by pika, which will then closing the channel and
        connection. The IOLoop is started again because this method is invoked
        when CTRL-C is pressed raising a KeyboardInterrupt exception. This
        exception stops the IOLoop which needs to be running for pika to
        communicate with RabbitMQ. All of the commands issued prior to starting
        the IOLoop will be buffered but not processed.

        """
        LOGGER.info('Stopping')
        self._closing = True
        self.stop_consuming()
        self._connection.ioloop.start()
        LOGGER.info('Stopped')

    def send_notification(self, ch, routing_key, state_id, target, phase, message):
        """
        Sends a notification message.
        """
        msg = {
            'slug': message[:80],
            'message': message,
            'phase': phase,
            'target': target,
        }
        props = pika.spec.BasicProperties()
        props.correlation_id = state_id
        props.reply_to = 'log'
        ch.basic_publish(
            exchange=self.c['EXCHANGE'],
            routing_key=routing_key,
            body=json.dumps(msg),
            properties=props)


# TODO: Delete this old function

def send_notification(ch, routing_key, state_id, target, phase, message):  # pragma no cover
    """
    Sends a notification message.
    """
    msg = {
        'slug': message[:80],
        'message': message,
        'phase': phase,
        'target': target,
    }
    props = pika.spec.BasicProperties()
    props.correlation_id = state_id
    props.reply_to = 'log'

    ch.basic_publish(
        exchange=MQ_CONF['EXCHANGE'],
        routing_key=routing_key,
        body=json.dumps(msg),
        properties=props)


def reject(ch, method, requeue=False):
    """
    Reject the message with the given `basic_deliver`
    """
    ch.basic_reject(
        method.delivery_tag,
        requeue=requeue)


def receive(ch, method, properties, body):
    """
    Callback for watching the FSM queue
    """
    out = logging.getLogger('recore')
    notify = logging.getLogger('recore.stdout')
    try:
        msg = json.loads(body)
    except ValueError:
        # Not JSON or not able to decode
        out.debug("Unable to decode message. Rejecting: %s" % body)
        reject(ch, method, False)
        notify.info("Unable to decode message. Rejected.")
        return
    topic = method.routing_key
    out.debug("Message: %s" % msg)

    if topic == 'job.create':
        id = None
        try:
            # We need to get the name of the temporary
            # queue to respond back on.
            notify.info("new job create for: %s" % msg['group'])
            out.info(
                "New job requested, starting release "
                "process for %s ..." % msg["group"])
            notify.debug("Job message: %s" % msg)
            reply_to = properties.reply_to

            # We do this lookup even though we have the ID
            # already. This is a sanity-check really to make sure we
            # were passed a valid playbook id.
            id = recore.job.create.release(
                ch, msg['playbook_id'], reply_to,
                msg.get('dynamic', {}))
        except KeyError, ke:
            notify.info("Missing an expected key in message: %s" % ke)
            out.error("Missing an expected key in message: %s" % ke)
            # FIXME: eating errors can be dangerous! Double check this is OK.
            return

        if id:
            # Skip this try/except until we work all the bugs out of the FSM
            # try:
            runner = recore.fsm.FSM(id)
            runner.start()
            signal.signal(signal.SIGINT, sighandler)
            # while runner.isAlive():
            #     runner.join(0.3)
            # except Exception, e:
            # notify.error(str(e))
    else:
        out.warn("Unknown routing key %s. Doing nothing ...")
        notify.info("IDK what this is: %s" % topic)

    notify.info("end receive() routine")
    out.debug("end receive() routine")


def sighandler(signal, frame):
    """
    If we get SIGINT on the CLI, we need to quit all the threads
    in our process group
    """
    import os
    import signal

    os.killpg(os.getpgid(0), signal.SIGQUIT)


def main():  # pragma no cover
    """
    Example main function.
    """
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    import json
    with open('../../fake-settings.json') as settings:
        config = json.load(settings)

    example = WinternewtBusClient(config)
    try:
        example.run()
    except KeyboardInterrupt:
        example.stop()


if __name__ == '__main__':
    main()
