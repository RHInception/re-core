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

"""
This represents a step.
"""


class Step(object):
    """This is a convenient little object to wrap steps. Let's stop
thinking about steps as just strings or dictionaries, and begin
thinking about them as proper objects.

    """
    def __init__(self, step, app_logger):
        self.app_logger = app_logger
        self._step = step
        self.params = {}
        self.app_logger.debug("Initializing step: %s" % str(step))

        if type(self._step) == str or \
           type(self._step) == unicode:
            self.app_logger.debug("Next step is a string. Split it and route it")
            (self.command, sep, self._subcommand) = self._step.partition(':')
        else:
            # It's a dictionary
            self.app_logger.debug("Next step has parameters to parse: %s" % self._step)
            _step_key = self._step.keys()[0]
            (self._command, sep, self._subcommand) = _step_key.partition(':')
            self.params = self._step[_step_key]
            notify.update(self._step[_step_key].get('notify', {}))

        self.filter.set_field("active_step", str(self))

        _params = {
            'command': self.command,
            'subcommand': self.subcommand,
            'hosts': self.active_sequence['hosts']
        }

        self.params.update(_params)

    def __str__(self):
        return "{CMD}:{SUB}".format(CMD=self.command, SUB=self.subcommand)

    @property
    def queue(self):
        return "worker.{command}".format(command=self.command)

    @property(self)
    def subcommand(self):
        return self._subcommand

    @property
    def command(self):
        return self._command
