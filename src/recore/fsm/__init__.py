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

import recore.mongo
import logging

class FSM(object):
    """The re-core Finite State Machine to oversee the execution of
a project's release steps."""

    def __init__(self, state_id, dynamic={}):
        """
        `state_id` - MongoDB ObjectID of the document holding release steps
        `dyanamic` - A hash of dynamic variables from the re-rest worker
        """
        self.app_logger = logging.getLogger('FSM-%s' % state_id)
        self.app_logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)
        self.app_logger.addHandler(handler)

        
