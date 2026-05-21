# -*- coding: utf-8 -*-
from django.conf import settings

#: Determines whether annotatable queryable properties apply Django's fetch modes.
APPLY_FETCH_MODE = getattr(settings, 'QUERYABLE_PROPERTIES_APPLY_FETCH_MODE', False)
