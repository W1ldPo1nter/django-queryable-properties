import pytest

from queryable_properties.query import (
    QUERYING_PROPERTIES_MARKER, AggregatePropertyChecker, QueryablePropertiesCompilerMixin,
)
from .app_management.models import (
    ApplicationWithClassBasedProperties, CategoryWithClassBasedProperties, VersionWithClassBasedProperties,
)


class TestAggregatePropertyChecker:

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
        (CategoryWithClassBasedProperties, 'circular', None, False),
    ])
    def test_is_aggregate_property(self, model, path, value, expected_result):
        assert AggregatePropertyChecker().is_aggregate_property((path, value), model) is expected_result


class TestQueryablePropertiesCompilerMixin:

    def test_setup_query(self):
        queryset = ApplicationWithClassBasedProperties.objects.select_properties('version_count')
        compiler = QueryablePropertiesCompilerMixin.inject_into_object(queryset.query.get_compiler(using=queryset.db))
        compiler.setup_query()
        assert tuple(compiler.annotation_col_map) == (QUERYING_PROPERTIES_MARKER, 'version_count')
