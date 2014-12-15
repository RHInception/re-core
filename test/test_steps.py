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

class TestSteps(TestCase):
    def test_new_Step_simple(self):
        step = "frob:Nicate"
        s = recore.mongo.Step(step)
        self.assertEqual(s.step_name, "frob:Nicate")
        self.assertEqual(s.command, 'frob')
        self.assertEqual(s.subcommand, 'Nicate')
        self.assertEqual(str(s), "frob:Nicate")

    def test_new_Step_parameters(self):
        step = {
            "frob:Nicate": {
                "megafrob": True
            }
        }

        s = recore.mongo.Step(step)
        self.assertEqual(s.step_name, "frob:Nicate")
        self.assertEqual(s.command, 'frob')
        self.assertEqual(s.subcommand, 'Nicate')
        self.assertEqual(str(s), "frob:Nicate")
