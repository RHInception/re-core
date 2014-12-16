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
import recore.contextfilter
import recore.constants
import recore.fsm
import logging
import os.path
import recore.mongo
import recore.amqp
import recore.fsm
import pika.exceptions
import pika.connection


def start_logging(log_file, log_level):
    # Create logger obj and set threshold
    recore_log = logging.getLogger('recore')
    # The core logger allows all levels of messages to flow into it
    # (logging.DEBUG)
    recore_log.setLevel(logging.DEBUG)

    # Create the default filter, this won't fill in any fields, but it
    # will let us use the same log message string
    recore_filter = recore.contextfilter.ContextFilter('recore')
    recore_log.addFilter(recore_filter)

    # Create the file log handler and set it's formatting string. The
    # file handler usually has a higher threshold than the logger
    # object. In this way DEBUG information won't appear in the file
    recore_file_handler = logging.FileHandler(log_file)
    recore_file_handler.setFormatter(recore.constants.LOG_FORMATTER)
    recore_file_handler.setLevel(log_level)
    recore_log.addHandler(recore_file_handler)

    # The stream handler logs events to the console (stdout/err). It's
    # final threshold is set to WARN so that process/flow information
    # isn't displayed, only warnings/errors/critical problems.
    recore_stream_handler = logging.StreamHandler()
    recore_stream_handler.setFormatter(recore.constants.LOG_FORMATTER)
    recore_stream_handler.setLevel(logging.INFO)
    recore_log.addHandler(recore_stream_handler)
    recore_log.info("Initialized core logging with level=%s and log file=%s" % (log_level, log_file))
    recore_stream_handler.setLevel(logging.WARN)


def parse_config(args):
    """Read in the config file. Or die trying"""
    try:
        config = recore.utils.parse_config_file(args.config)
        start_logging(config.get(
            'LOGFILE', 'recore.log'), config.get('LOGLEVEL', 'INFO'))
        notify = logging.getLogger('recore')
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

        recore.amqp.CONF = config
        recore.amqp.MQ_CONF = config['MQ']

        # Any trigger provided on the CLI? That overrides config file
        if 'triggers' in args and args.triggers:
            notify.debug("Evaluating discovered triggers in CLI options")
            try:
                triggers = recore.utils.parse_config_file(
                    os.path.realpath(args.triggers))
                recore.fsm.TRIGGERS = triggers.get('STEP_TRIGGERS', [])
                notify.debug("Evaluated triggers: %s" % str(recore.fsm.TRIGGERS))
            except Exception, e:
                notify.error("Couldn't parse triggers in {TRIGGER_FILE}. Error: {ERROR}".format(
                    TRIGGER_FILE=args.triggers,
                    ERROR=str(e)))
                raise e
        elif config.get('TRIGGERS', None):
            notify.debug("Evaluating discovered triggers in the main config file")
            try:
                triggers = recore.utils.parse_config_file(
                    os.path.realpath(config['TRIGGERS']))
                recore.fsm.TRIGGERS = triggers.get('STEP_TRIGGERS', [])
                notify.debug("Evaluated triggers: %s" % str(recore.fsm.TRIGGERS))
            except Exception, e:
                notify.error("Couldn't parse triggers in {TRIGGER_FILE}. Error: {ERROR}".format(
                    TRIGGER_FILE=config['TRIGGERS'],
                    ERROR=str(e)))
                raise e

    except IOError, e:
        print "ERROR config doesn't exist: %s" % e
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
    pika.connection.PRODUCT = recore.constants.AMQP_COMPONENT
    import pymongo.errors

    config = parse_config(args)

    out = logging.getLogger('recore')
    try:
        recore.mongo.init_mongo(config['DB'])
    except pymongo.errors.ConnectionFailure, cfe:
        out.fatal("Connection failiure to Mongo: %s. Exiting ..." % cfe)
        raise SystemExit(1)
    except pymongo.errors.PyMongoError, cfe:
        out.fatal("Unknown failiure with Mongo: %s. Exiting ..." % cfe)
        raise SystemExit(1)

    try:
        connection = recore.amqp.WinternewtBusClient(config)
        connection.run()
    except KeyError, ke:
        out.fatal("Missing a required key in MQ config: %s" % ke)
        raise SystemExit(1)
    except pika.exceptions.ProbableAuthenticationError, paex:
        out.fatal("Authentication issue connecting to AMQP: %s" % paex)
        raise SystemExit(1)
    except (
            pika.exceptions.ProtocolSyntaxError,
            pika.exceptions.AMQPError), ex:
        out.fatal("Unknown issue connecting to AMQP: %s" % ex)
        raise SystemExit(1)
    except KeyboardInterrupt:
        out.info("KeyboardInterrupt sent.")
        connection.stop()
        raise SystemExit(0)

######################################################################
# pika spews messages about logging handlers by default. So we're just
# going to set the level to CRITICAL so we don't see most of them.
logging.getLogger('pika').setLevel(logging.CRITICAL)
