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
import recore.fsm
import logging
import os.path
import recore.mongo
import recore.amqp
import sys
import pika.exceptions
import pika.connection

RE_COMPONENT = "RE-CORE"


def start_logging(log_file, log_level):
    # First the file logging
    output = logging.getLogger('recore')
    output.setLevel(logging.getLevelName(log_level))
    log_handler = logging.FileHandler(log_file)
    log_handler.setLevel(logging.getLevelName(log_level))
    log_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - %(levelname)s - %(message)s'))
    output.addHandler(log_handler)
    output.debug("initialized logger")

    # And now the stdout logging
    out2 = logging.getLogger('recore.stdout')
    out2.setLevel(logging.getLevelName(log_level))
    lh2 = logging.StreamHandler(sys.stdout)
    lh2.setFormatter(logging.Formatter(
        '%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - %(levelname)s - %(message)s'))
    out2.addHandler(lh2)
    out2.debug("initialized stdout logger")


def parse_config(config_path):
    """Read in the config file. Or die trying"""
    try:
        config = recore.utils.parse_config_file(config_path)
        start_logging(config.get(
            'LOGFILE', 'recore.log'), config.get('LOGLEVEL', 'INFO'))
        notify = logging.getLogger('recore.stdout')
        notify.debug('Parsed configuration file')

        # Initialize the FSM logger, only if RELEASE_LOG_DIR isn't
        # 'null' in the settings file.
        #
        # TODO: This would be better handled by setting
        # 'recore.fsm.release' levels and then letting the sub-loggers
        # propagate the level decision to the recore.fsm.release
        # level.
        if config.get('RELEASE_LOG_DIR', None):
            recore.fsm.RELEASE_LOG_DIR = os.path.realpath(config.get('RELEASE_LOG_DIR'))

    except IOError:
        print "ERROR config doesn't exist"
        raise SystemExit(1)
    except ValueError, vex:
        print "ERROR config file is not valid json: %s" % vex
        raise SystemExit(1)
    return config


def main(args):  # pragma: no cover
    """
    Main script entry point.

    *Note*: Not covered for unittests as it glues tested code together.
    """
    pika.connection.PRODUCT = RE_COMPONENT
    import pymongo.errors

    config = parse_config(args.config)

    out = logging.getLogger('recore')
    notify = logging.getLogger('recore.stdout')
    try:
        recore.mongo.init_mongo(config['DB'])
    except pymongo.errors.ConnectionFailure, cfe:
        out.fatal("Connection failiure to Mongo: %s. Exiting ..." % cfe)
        notify.fatal("Connection failiure to Mongo: %s. Exiting ..." % cfe)
        raise SystemExit(1)
    except pymongo.errors.PyMongoError:
        out.fatal("Unknown failiure with Mongo: %s. Exiting ..." % cfe)
        notify.fatal("Unknown failiure with Mongo: %s. Exiting ..." % cfe)
        raise SystemExit(1)

    try:
        connection = recore.amqp.WinternewtBusClient(config)
        connection.run()
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
    except KeyboardInterrupt:
        out.info("KeyboardInterrupt sent.")
        notify.info("Keyboard Interrupt sent.")
        connection.stop()
        raise SystemExit(0)

    out.info('FSM fully initialized')
    notify.info('FSM fully initialized')

######################################################################
# pika spews messages about logging handlers by default. So we're just
# going to set the level to CRITICAL so we don't see most of them.
logging.getLogger('pika').setLevel(logging.CRITICAL)
