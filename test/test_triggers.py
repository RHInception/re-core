# Copyright (C) 2014 SEE AUTHORS FILE
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

from . import TestCase, unittest

import recore.mongo
import json

class TestTriggers(TestCase):
    def setUp(self):
        with open('./examples/triggers/triggers.trigger.json') as f:
            self.triggers = json.load(f)['STEP_TRIGGERS']

    def test_new_Trigger(self):
        for trigger in self.triggers:
            t = recore.mongo.Trigger(trigger, '123456789abcdefg')
            self.assertEqual(t.step_name, "sleep:seconds")
            self.assertEqual(t.command, 'sleep')
            self.assertEqual(t.subcommand, 'seconds')
            self.assertEqual(str(t), "sleep:seconds")
