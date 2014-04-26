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

import os
import json


def parse_config_file(path):
    try:
        return json.loads(open(os.path.expanduser(path)).read())
    except IOError:
        raise IOError("Path to config file doesn't exist: %s" % path)


def load_json_str(jstr):
    """
    Internalize the json content object (`jstr`) into a native Python
    datastructure and return it.
    """
    return json.loads(str(jstr))


def create_json_str(input_ds, **kwargs):
    """
    Load a native Python datastructure into a json formatted string
    and return it.
    """
    if type(input_ds) not in (dict, list):
        raise ValueError('create_json_str will only work with a dict or list')
    return json.dumps(input_ds, **kwargs)
