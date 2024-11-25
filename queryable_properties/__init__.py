# encoding: utf-8
"""Write Django model properties that can be used in database queries."""

from __future__ import unicode_literals

from .compat import apps_config

if not hasattr(apps_config, 'APPS_MODULE_NAME'):
    default_app_config = 'queryable_properties.apps.QueryablePropertiesConfig'

__version__ = '1.9.3'
__author__ = 'Marcus Klöpfel'
__copyright__ = 'Copyright 2024, Marcus Klöpfel'
__license__ = 'BSD'
__maintainer__ = 'Marcus Klöpfel'
__email__ = 'marcus.kloepfel@gmail.com'
__status__ = 'Production/Stable'
