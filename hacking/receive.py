#!/usr/bin/env python
import pika
import logging
import sys
import json
import os

components = [ 'fsm', 'worker', 'logger', 'rest', 'notification' ]
comp_descs = [
    'job.create/release.step.*.*',
    'plugin.shexec.start',
    '#',
    'n/a',
    'notification'
    ]

def _setup(host, name, password, exchange):
    creds = pika.credentials.PlainCredentials(name, password)
    connection = pika.BlockingConnection(pika.ConnectionParameters(
            host=host,
            credentials=creds))
    channel = connection.channel()
    channel.exchange_declare(exchange=exchange,
                             durable=True,
                             exchange_type='topic')
    return (channel, connection)

def repl(mq_config):
    while True:
        print "+-----------------------------+"
        print "| Receive as which component? |"
        print "+-----------------------------+"
        i = 0
        for comp in components:
            print "%s) %s [%s]" % (i, comp, comp_descs[i])
            i += 1
        print "q) Quit"

        receive_as = raw_input("\033[00;32mCOMPONENT>>> \033[0m")

        valid_choices = map(str, xrange(len(components)))
        valid_choices.extend(['Q', 'q'])
        if receive_as not in valid_choices:
            print "\033[00;31mInvalid choice. Pick from the above menu\033[0m"
            continue
        elif receive_as.lower() == "q":
            break
        else:
            print "Receiving as component: %s\n" % components[int(receive_as)]

        (channel, connection) = _setup(mq_config['SERVER'],
                                       mq_config['NAME'],
                                       mq_config['PASSWORD'],
                                       mq_config['EXCHANGE'])
        result = channel.queue_declare(durable=True, queue='%s queue' % components[int(receive_as)])
        queue_name = result.method.queue

        channel.basic_consume(callback,
                              queue=queue_name,
                              no_ack=True)
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.close()
            connection.close()
            pass

######################################################################
def callback(ch, method, properties, body):
    print "Topic: %s\nMessage: %s\n" % (method.routing_key, body,)
    # import pdb
    # pdb.set_trace()

######################################################################
logging.getLogger('pika').setLevel(logging.CRITICAL)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print "usage: %s path/to/re-core/config/file.json"
        sys.exit(1)
    else:
        config = sys.argv[1]
        try:
            mq_config = json.loads(open(os.path.expanduser(config), 'r').read())['MQ']
        except Exception, e:
            print "usage: %s path/to/re-core/config/file.json"
            print "Error loading config:"
            print e
            sys.exit(1)
    repl(mq_config)
    sys.exit(0)
