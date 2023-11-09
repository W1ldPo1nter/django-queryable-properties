# -*- coding: utf-8 -*-

import pytest
from django import VERSION as DJANGO_VERSION

from queryable_properties.query import AggregatePropertyChecker
from .app_management.models import (
    ApplicationWithClassBasedProperties, CategoryWithClassBasedProperties, VersionWithClassBasedProperties,
)


class TestAggregatePropertyChecker(object):

    def test_initializer(self):
        checker = AggregatePropertyChecker()
        assert checker.func == checker.is_aggregate_property

    @pytest.mark.parametrize('model, path, value, expected_result', [
        # Not a queryable property
        (ApplicationWithClassBasedProperties, 'non_existent', None, False),
        # Queryable property with required aggregate annotation
        (ApplicationWithClassBasedProperties, 'version_count', 1337, True),
        # Queryable property without required annotation
        (VersionWithClassBasedProperties, 'version', '1.2.3', False),
        # Self-references don't lead to infinite loops
        (CategoryWithClassBasedProperties, 'circular', None, DJANGO_VERSION < (1, 8)),
    ])
    def test_is_aggregate_property(self, model, path, value, expected_result):
        assert AggregatePropertyChecker().is_aggregate_property((path, value), model) is expected_result
