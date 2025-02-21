# -*- coding: utf-8 -*-
"""Reusable pytest marks for tests and/or parametrizations."""

import pytest
from django import VERSION as DJANGO_VERSION


skip_if_no_expressions = pytest.mark.skipif(DJANGO_VERSION < (1, 8),
                                            reason="Expression-based annotations didn't exist before Django 1.8")
skip_if_no_output_fields = pytest.mark.skipif(DJANGO_VERSION < (1, 8),
                                              reason="Output fields couldn't be declared before Django 1.8")
skip_if_no_subqueries = pytest.mark.skipif(DJANGO_VERSION < (1, 11),
                                           reason="Explicit subqueries didn't exist before Django 1.11")
skip_if_no_composite_pks = pytest.mark.skipif(DJANGO_VERSION < (5, 2),
                                              reason="Composite PKs didn't exist before Django 5.2")
