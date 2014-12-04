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

import recore.constants
import recore.contextfilter
import logging

class TestContextFilter(TestCase):
    def test_context_filter_lookup_good(self):
        """We can lookup filters by name"""
        l = logging.getLogger(__name__)
        c = recore.contextfilter.ContextFilterUnique(__name__)
        l.addFilter(c)
        the_filter = recore.contextfilter.get_logger_filter(__name__, __name__)
        assert c is the_filter

    def test_context_filter_lookup_good_no_name(self):
        """We can lookup filters without using a name"""
        l = logging.getLogger(__name__ + "no_name")
        c = recore.contextfilter.ContextFilterUnique(__name__ + "no_name")
        l.addFilter(c)
        the_filter = recore.contextfilter.get_logger_filter(__name__ + "no_name")
        assert c is the_filter

    def test_context_filter_lookup_bad(self):
        """We are able to detect when no filters are attached"""
        l = logging.getLogger(__name__ + "no_filter")
        the_filter = recore.contextfilter.get_logger_filter(__name__ + "no_filter")
        assert the_filter is False

    def test_context_filter_lookup_bad(self):
        """We are able to detect when a requested filter doesn't exist"""
        l = logging.getLogger(__name__ + "no_filter")
        the_filter = recore.contextfilter.get_logger_filter(__name__ + "no_filter", "coolfilterbro")
        assert the_filter is False

    def test_singleton_context_filter(self):
        """The context-filter with class-level storage works"""
        l = logging.getLogger(__name__ + "singleton")
        l.setLevel(logging.DEBUG)
        h = logging.StreamHandler()
        h.setFormatter(recore.constants.LOG_FORMATTER)
        l.addHandler(h)
        c = recore.contextfilter.ContextFilter(__name__ + "singleton")
        l.addFilter(c)
        l.debug("Test")
