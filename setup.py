#!/usr/bin/env python
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
"""
Build script.
"""

import os.path

from setuptools import setup, find_packages


setup(
    name='recore',
    version='0.0.1',
    author='See AUTHORS',
    url='https://github.com/RHInception/re-core',
    license='AGPLv3',
    zip_safe=False,
    package_dir={
        'recore': os.path.join('src', 'recore')
    },
    packages=find_packages('src'),
    install_requires=[
        'flask>=0.10',
    ],
    classifiers=[
        ('License :: OSI Approved :: GNU Affero General Public '
         'License v3 or later (AGPLv3+)'),
        'Development Status :: 5 - Production/Stable',
        'Programming Language :: Python',
    ],

)
