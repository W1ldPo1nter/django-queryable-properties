# encoding: utf-8
import pytest

from queryable_properties.query import QueryablePropertiesQueryMixin, QueryablePropertyReference
from tests.models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                          CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties,
                          VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)


class TestResolveQueryableProperty(object):

    @pytest.mark.parametrize('model, path, expected_property, expected_lookups', [
        # No relation involved
        (VersionWithClassBasedProperties, ['version'], VersionWithClassBasedProperties.version, []),
        (VersionWithDecoratorBasedProperties, ['version'], VersionWithDecoratorBasedProperties.version, []),
        (VersionWithClassBasedProperties, ['version', 'lower', 'exact'],
         VersionWithClassBasedProperties.version, ['lower', 'exact']),
        (VersionWithDecoratorBasedProperties, ['version', 'lower', 'exact'],
         VersionWithDecoratorBasedProperties.version, ['lower', 'exact']),
        # FK forward relation
        (VersionWithClassBasedProperties, ['application', 'version_count'],
         ApplicationWithClassBasedProperties.version_count, []),
        (VersionWithDecoratorBasedProperties, ['application', 'version_count'],
         ApplicationWithDecoratorBasedProperties.version_count, []),
        (VersionWithClassBasedProperties, ['application', 'major_sum', 'gt'],
         ApplicationWithClassBasedProperties.major_sum, ['gt']),
        (VersionWithDecoratorBasedProperties, ['application', 'major_sum', 'gt'],
         ApplicationWithDecoratorBasedProperties.major_sum, ['gt']),
        # FK reverse relation
        (ApplicationWithClassBasedProperties, ['versions', 'major_minor'],
         VersionWithClassBasedProperties.major_minor, []),
        (ApplicationWithDecoratorBasedProperties, ['versions', 'major_minor'],
         VersionWithDecoratorBasedProperties.major_minor, []),
        (ApplicationWithClassBasedProperties, ['versions', 'version', 'lower', 'contains'],
         VersionWithClassBasedProperties.version, ['lower', 'contains']),
        (ApplicationWithDecoratorBasedProperties, ['versions', 'version', 'lower', 'contains'],
         VersionWithDecoratorBasedProperties.version, ['lower', 'contains']),
        # M2M forward relation
        (ApplicationWithClassBasedProperties, ['categories', 'circular'],
         CategoryWithClassBasedProperties.circular, []),
        (ApplicationWithDecoratorBasedProperties, ['categories', 'circular'],
         CategoryWithDecoratorBasedProperties.circular, []),
        (ApplicationWithClassBasedProperties, ['categories', 'circular', 'exact'],
         CategoryWithClassBasedProperties.circular, ['exact']),
        (ApplicationWithDecoratorBasedProperties, ['categories', 'circular', 'exact'],
         CategoryWithDecoratorBasedProperties.circular, ['exact']),
        # M2M reverse relation
        (CategoryWithClassBasedProperties, ['applications', 'major_sum'],
         ApplicationWithClassBasedProperties.major_sum, []),
        (CategoryWithDecoratorBasedProperties, ['applications', 'major_sum'],
         ApplicationWithDecoratorBasedProperties.major_sum, []),
        (CategoryWithClassBasedProperties, ['applications', 'version_count', 'lt'],
         ApplicationWithClassBasedProperties.version_count, ['lt']),
        (CategoryWithDecoratorBasedProperties, ['applications', 'version_count', 'lt'],
         ApplicationWithDecoratorBasedProperties.version_count, ['lt']),
        # Multiple relations
        (CategoryWithClassBasedProperties, ['applications', 'versions', 'application', 'categories', 'circular'],
         CategoryWithClassBasedProperties.circular, []),
        (CategoryWithDecoratorBasedProperties, ['applications', 'versions', 'application', 'categories', 'circular'],
         CategoryWithDecoratorBasedProperties.circular, []),
        (VersionWithClassBasedProperties, ['application', 'categories', 'circular', 'in'],
         CategoryWithClassBasedProperties.circular, ['in']),
        (VersionWithDecoratorBasedProperties, ['application', 'categories', 'circular', 'in'],
         CategoryWithDecoratorBasedProperties.circular, ['in']),
    ])
    def test_successful(self, model, path, expected_property, expected_lookups):
        mixin = QueryablePropertiesQueryMixin()
        mixin.model = model
        expected_ref = QueryablePropertyReference(expected_property, expected_property.model,
                                                  tuple(path[:-len(expected_lookups) - 1]))
        assert mixin._resolve_queryable_property(path) == (expected_ref, expected_lookups)

    @pytest.mark.parametrize('model, path', [
        # No relation involved
        (VersionWithClassBasedProperties, ['non_existent']),
        (VersionWithDecoratorBasedProperties, ['non_existent']),
        (VersionWithClassBasedProperties, ['major']),
        (VersionWithDecoratorBasedProperties, ['major']),
        # FK forward relation
        (VersionWithClassBasedProperties, ['application', 'non_existent', 'exact']),
        (VersionWithDecoratorBasedProperties, ['application', 'non_existent', 'exact']),
        (VersionWithClassBasedProperties, ['application', 'name']),
        (VersionWithDecoratorBasedProperties, ['application', 'name']),
        # FK reverse relation
        (ApplicationWithClassBasedProperties, ['versions', 'non_existent']),
        (ApplicationWithDecoratorBasedProperties, ['versions', 'non_existent']),
        (ApplicationWithClassBasedProperties, ['versions', 'minor', 'gt']),
        (ApplicationWithDecoratorBasedProperties, ['versions', 'minor', 'gt']),
        # M2M forward relation
        (ApplicationWithClassBasedProperties, ['categories', 'non_existent']),
        (ApplicationWithDecoratorBasedProperties, ['categories', 'non_existent']),
        (ApplicationWithClassBasedProperties, ['categories', 'name']),
        (ApplicationWithDecoratorBasedProperties, ['categories', 'name']),
        # M2M reverse relation
        (CategoryWithClassBasedProperties, ['applications', 'non_existent']),
        (CategoryWithDecoratorBasedProperties, ['applications', 'non_existent']),
        (CategoryWithClassBasedProperties, ['applications', 'name']),
        (CategoryWithDecoratorBasedProperties, ['applications', 'name']),
        # Non existent relation
        (VersionWithClassBasedProperties, ['non_existent_relation', 'non_existent', 'in']),
        (VersionWithDecoratorBasedProperties, ['non_existent_relation', 'non_existent', 'in']),
    ])
    def test_unsuccessful(self, model, path):
        mixin = QueryablePropertiesQueryMixin()
        mixin.model = model
        assert mixin._resolve_queryable_property(path) == (None, [])
