# -*- coding: utf-8 -*-
"""Import interface for the mock library."""

try:
    from unittest.mock import *  # noqa
except ImportError:
    from mock import *  # noqa
