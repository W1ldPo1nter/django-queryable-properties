# -*- coding: utf-8 -*-
import six
from django.conf import settings as django_settings

settings = type('Settings', (object,), {name: property(getter) for name, getter in six.iteritems({
    'APPLY_FETCH_MODE': lambda self: getattr(django_settings, 'QUERYABLE_PROPERTIES_APPLY_FETCH_MODE', False),
})})()
