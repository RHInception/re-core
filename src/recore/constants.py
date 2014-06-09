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

NEW_STATE_RECORD = {
    # Meta
    'reply_to': None,
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
}
