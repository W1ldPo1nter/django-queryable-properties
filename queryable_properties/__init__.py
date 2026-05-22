# encoding: utf-8
"""Write Django model properties that can be used in database queries."""

from __future__ import unicode_literals

import six
from django.conf import settings as django_settings

VERSION = (1, 12, 1)

__version__ = '.'.join(map(str, VERSION))
__author__ = 'Marcus Klöpfel'
__copyright__ = 'Copyright 2025, Marcus Klöpfel'
__license__ = 'BSD'
__maintainer__ = 'Marcus Klöpfel'
__email__ = 'marcus.kloepfel@gmail.com'
__status__ = 'Production/Stable'

settings = type('Settings', (object,), {name: property(getter) for name, getter in six.iteritems({
    'APPLY_FETCH_MODE': lambda self: getattr(django_settings, 'QUERYABLE_PROPERTIES_APPLY_FETCH_MODE', False),
})})()
