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

# I HEARD YOU LIKE PASSING UNITTESTS (keep reading)
#
# If you enjoy passing unittests, and you add a field to the new state
# record, make sure you account for that in the mongo tests. Most
# likely you're going to want to look at
# test/test_mongo.py:test_initialize_state(). There's an
# "assert_called_once_with" that expects each of these keys to be
# present.
NEW_STATE_RECORD = {
    # Meta
    'reply_to': None,
    'user_id': None,
    'group': None,
    'created': None,
    'ended': None,
    'failed': False,
    'dynamic': {},
    'playbook_id': None,

    # Running (or about to/just ran) step
    'active_step': None,

    # All execution sequences, from the playbook
    'execution': [],
    # Completed execution sequences
    'executed': [],
    # Currently running sequence
    'active_sequence': {},

    # Any triggers the core was configured with when the deployment
    # started
    'triggers': [],
}

######################################################################
# Logging/application identification stuff
#
# For application logging
APP_COMPONENT = "recore"

# For AMQP channel/connection identification
AMQP_COMPONENT = "RE-CORE"

LOG_STRING = '%(date_string)s - app_component="%(app_component)s" - source_ip="%(source_ip)s" - log_level="%(levelname)s" - playbook_id="%(playbook_id)s" - deployment_id="%(deployment_id)s" - user_id="%(user_id)s" - active_step="%(active_step)s" - deploy_phase="%(deploy_phase)s" - message="%(message)s"'
LOG_FORMATTER = logging.Formatter(LOG_STRING)
