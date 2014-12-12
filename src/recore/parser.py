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

import argparse
import recore

description = """Release Engine CORE Component. A multi-threaded finite state machine
(FSM) which executes playbooks."""

epilog = """Configuration and trigger files are in JSON format. Validation
errors? Make sure you're using double-quote characters in strings. Try
out http://jsonlint.com/ or 'python -m json.tool < CONFIG.json' to get
some more insight."""

parser = argparse.ArgumentParser(
    description=description,
    epilog=epilog)

parser.add_argument('-c', '--config', required=True, help='Config file to use')
parser.add_argument('-t', '--trigger', help='Path to trigger configuration')

parser.set_defaults(func=recore.main)
args = parser.parse_args()
