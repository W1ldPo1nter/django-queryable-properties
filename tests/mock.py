# -*- coding: utf-8 -*-
"""Import interface for the mock library."""

from __future__ import absolute_import

try:
    from unittest.mock import *  # noqa
except ImportError:
    from mock import *  # noqa
