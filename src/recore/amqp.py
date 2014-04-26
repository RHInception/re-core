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

MQ_CONF = {}
connection = None

def init_amqp(mq):
    """Open a channel to our AMQP server"""
    import recore.amqp
    recore.amqp.MQ_CONF = mq
    out = logging.getLogger('recore.amqp')
    # notify = logging.getLogger('recore.stdout')

    (channel, connection) = recore.utils.connect_mq(
        name=mq['NAME'],
        password=mq['PASSWORD'],
        server=mq['SERVER'],
        exchange=mq['EXCHANGE'])
    connect_string = "amqp://%s:******@%s:%s/%s" % (
        mq['NAME'], mq['SERVER'], mq['PORT'], mq['EXCHANGE'])
    out.debug("Opened AMQP connection: %s" % connect_string)

    receive_as = mq['QUEUE']
    result = channel.queue_declare(durable=True, queue=receive_as)
    queue_name = result.method.queue
    recore.amqp.connection = connection
    return (channel, connection, queue_name)

def connect_mq(name=None, password=None, server=None, exchange=None):
    """
    Return channel and connection objects hooked into our message bus

    `name` - Username to connect with
    `password` - Password to authenticate with
    `server` - Hostname of the actual message bus
    `exchange` - Exchange to connect to on the bus

    Returns a 2-tuple of `channel` and `connection` objects
    """
    out = logging.getLogger('recore')
    creds = pika.credentials.PlainCredentials(name, password)
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        host=str(server),
        credentials=creds))
    out.debug("Connection to MQ opened.")
    channel = connection.channel()
    out.debug("MQ channel opened. Declaring exchange ...")
    channel.exchange_declare(exchange=exchange,
                             durable=True,
                             exchange_type='topic')
    out.debug("Exchange declared.")
    return (channel, connection)
