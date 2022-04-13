# encoding: utf-8

from datetime import date

import pytest
from django import VERSION as DJANGO_VERSION

from ..app_management.models import (
    ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties, CategoryWithClassBasedProperties,
    CategoryWithDecoratorBasedProperties, VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties,
)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class TestAggregateAnnotations(object):

    @pytest.mark.parametrize('model, filters, expected_version_counts', [
        (ApplicationWithClassBasedProperties, {}, {3, 4}),
        (ApplicationWithClassBasedProperties, {'name__contains': 'cool'}, {3}),
        (ApplicationWithClassBasedProperties, {'version_count__gt': 3}, {4}),
        (ApplicationWithClassBasedProperties, {'version_count': 5}, set()),
        (ApplicationWithDecoratorBasedProperties, {}, {3, 4}),
        (ApplicationWithDecoratorBasedProperties, {'name__contains': 'cool'}, {3}),
        (ApplicationWithDecoratorBasedProperties, {'version_count__gt': 3}, {4}),
        (ApplicationWithDecoratorBasedProperties, {'version_count': 5}, set()),
    ])
    def test_values_to_limit_fields(self, model, filters, expected_version_counts):
        # Delete one version to create distinct version counts
        model.objects.get(name__contains='cool').versions.all()[0].delete()
        queryset = model.objects.filter(**filters).select_properties('version_count').values('version_count')
        version_counts = set(obj_dict['version_count'] for obj_dict in queryset)
        assert version_counts == expected_version_counts

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_values_for_custom_grouping(self, model):
        values = model.objects.values('common_data').select_properties('version_count')
        assert len(values) == 1
        assert values[0]['version_count'] == 8

    @pytest.mark.parametrize('model, values, property_name, filter_value, expected_count', [
        (ApplicationWithClassBasedProperties, ('common_data',), 'version_count', 7, 1),
        (ApplicationWithDecoratorBasedProperties, ('common_data',), 'version_count', 7, 1),
        (CategoryWithClassBasedProperties, ('pk', 'applications__pk'), 'applications__version_count', 4, 2),
        (CategoryWithDecoratorBasedProperties, ('pk', 'applications__pk'), 'applications__version_count', 4, 2),
    ])
    def test_values_without_property_selection(self, model, values, property_name, filter_value, expected_count):
        version_model = (VersionWithClassBasedProperties if 'ClassBased' in model.__name__
                         else VersionWithDecoratorBasedProperties)
        # Delete one version to create distinct version counts
        version_model.objects.get(application__name__contains='cool', major=2).delete()
        queryset = model.objects.values(*values).filter(**{property_name: filter_value})
        assert len(queryset) == expected_count
        assert len(set(tuple(obj_dict.items()) for obj_dict in queryset)) == expected_count
        assert all(set(obj_dict) == set(values) for obj_dict in queryset)

    @pytest.mark.parametrize('model, values, property_name, select, expected_count', [
        (ApplicationWithClassBasedProperties, ('common_data',), 'version_count', False, 1),
        (ApplicationWithDecoratorBasedProperties, ('common_data',), 'version_count', False, 1),
        (ApplicationWithClassBasedProperties, ('common_data', 'version_count'), 'version_count', True, 2),
        (ApplicationWithDecoratorBasedProperties, ('common_data', 'version_count'), 'version_count', True, 2),
        (CategoryWithClassBasedProperties, ('pk', 'applications__pk'), 'applications__version_count', False, 3),
        (CategoryWithDecoratorBasedProperties, ('pk', 'applications__pk'), 'applications__version_count', False, 3),
    ])
    def test_values_with_order_by_property(self, model, values, property_name, select, expected_count):
        # In Django versions below 1.8, annotations used for ordering MUST be
        # selected, which expectedly tinkers with the GROUPING.
        expected_count += int(DJANGO_VERSION < (1, 8) and not select and property_name == 'version_count')
        queryset = model.objects.order_by(property_name)
        if select:
            queryset = queryset.select_properties(property_name)
        queryset = queryset.values(*values)
        assert len(queryset) == expected_count
        assert all(set(obj_dict) == set(values) for obj_dict in queryset)

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_distinct_property_values(self, model):
        queryset = model.objects.select_properties('version_count').values('version_count').distinct()
        assert queryset.count() == len(queryset) == 1
        assert queryset[0]['version_count'] == 4

    @pytest.mark.parametrize('model, filters, expected_version_counts', [
        (ApplicationWithClassBasedProperties, {}, {3, 4}),
        (ApplicationWithClassBasedProperties, {'name__contains': 'cool'}, {3}),
        (ApplicationWithClassBasedProperties, {'version_count__gt': 3}, {4}),
        (ApplicationWithClassBasedProperties, {'version_count': 5}, set()),
        (ApplicationWithDecoratorBasedProperties, {}, {3, 4}),
        (ApplicationWithDecoratorBasedProperties, {'name__contains': 'cool'}, {3}),
        (ApplicationWithDecoratorBasedProperties, {'version_count__gt': 3}, {4}),
        (ApplicationWithDecoratorBasedProperties, {'version_count': 5}, set()),
    ])
    def test_values_list(self, model, filters, expected_version_counts):
        # Delete one version to create distinct version counts
        model.objects.get(name__contains='cool').versions.all()[0].delete()
        queryset = model.objects.filter(**filters).select_properties('version_count').values_list('version_count',
                                                                                                  flat=True)
        assert set(queryset) == expected_version_counts

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    @pytest.mark.parametrize('select, order_by, values_list, expected_count', [
        ((), ('version_count',), (), 2),
        ((), ('-version_count',), ('common_data',), 1),
        (('version_count',), ('version_count',), (), 2),
        (('version_count',), ('-version_count',), ('common_data',), 2),
        (('version_count',), ('version_count',), ('common_data', 'version_count'), 2),
        (('major_sum',), ('-version_count',), ('common_data', 'name', 'major_sum'), 2),
    ])
    def test_values_list_with_order_by_property(self, model, select, order_by, values_list, expected_count):
        # In Django versions below 1.8, annotations used for ordering MUST be
        # selected, which expectedly tinkers with the GROUPING.
        expected_count += int(DJANGO_VERSION < (1, 8) and bool(values_list) and not select)
        expected_tuple_len = len(values_list) if values_list else (3 + len(select))
        queryset = model.objects.order_by(*order_by)
        if select:
            queryset = queryset.select_properties(*select)
        queryset = queryset.values_list(*values_list)
        assert len(queryset) == expected_count
        assert all(len(obj_tuple) == expected_tuple_len for obj_tuple in queryset)

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    @pytest.mark.parametrize('select, order_by, name, expected_results', [
        ((), ('version_count',), 'common_data', [0, 0]),
        (('version_count',), ('-version_count',), 'common_data', [0, 0]),
        (('version_count',), ('version_count',), 'version_count', [4, 4]),
        (('major_sum',), ('-version_count',), 'major_sum', [5, 5]),
    ])
    def test_flat_list_with_order_by_property(self, model, select, order_by, name, expected_results):
        queryset = model.objects.order_by('pk', *order_by)
        if select:
            queryset = queryset.select_properties(*select)
        assert list(queryset.values_list(name, flat=True)) == expected_results

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="dates() couldn't be used with annotations before Django 1.8")
    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_dates(self, model):
        model.objects.all()[0].versions.filter(version='1.3.0').delete()
        queryset = model.objects.dates('support_start_date', 'day')
        assert list(queryset) == [date(2017, 1, 1), date(2018, 1, 1)]


@pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
class TestExpressionAnnotations(object):

    @pytest.mark.parametrize('model, filters, expected_versions', [
        (VersionWithClassBasedProperties, {}, {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (VersionWithClassBasedProperties, {'patch': 0}, {'1.3.0', '2.0.0'}),
        (VersionWithClassBasedProperties, {'major_minor': '1.3'}, {'1.3.0', '1.3.1'}),
        (VersionWithClassBasedProperties, {'version': '2.0.0'}, {'2.0.0'}),
        (VersionWithDecoratorBasedProperties, {}, {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (VersionWithDecoratorBasedProperties, {'patch': 0}, {'1.3.0', '2.0.0'}),
        (VersionWithDecoratorBasedProperties, {'major_minor': '1.3'}, {'1.3.0', '1.3.1'}),
        (VersionWithDecoratorBasedProperties, {'version': '2.0.0'}, {'2.0.0'}),
    ])
    def test_values_to_limit_fields(self, model, filters, expected_versions):
        queryset = model.objects.filter(**filters).select_properties('version').values('version')
        versions = set(obj_dict['version'] for obj_dict in queryset)
        assert versions == expected_versions

    @pytest.mark.skipif(DJANGO_VERSION < (1, 11), reason="Explicit subqueries didn't exist before Django 1.11")
    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_group_by_property(self, model):
        queryset = model.objects.select_properties('highest_version').values('highest_version')
        queryset = queryset.select_properties('version_count')
        assert queryset.count() == len(queryset) == 1
        assert queryset[0]['version_count'] == 8

    @pytest.mark.parametrize('model, values, property_name, filter_value, expected_count', [
        (VersionWithClassBasedProperties, ('major',), 'changes_or_default', '(No data)', 6),
        (VersionWithDecoratorBasedProperties, ('major',), 'changes_or_default', '(No data)', 6),
        (ApplicationWithClassBasedProperties, ('name',), 'versions__changes_or_default', '(No data)', 6),
        (ApplicationWithDecoratorBasedProperties, ('name',), 'versions__changes_or_default', '(No data)', 6),
    ])
    def test_values_without_property_selection(self, model, values, property_name, filter_value, expected_count):
        queryset = model.objects.values(*values).filter(**{property_name: filter_value})
        assert len(queryset) == expected_count
        assert all(property_name not in obj_dict for obj_dict in queryset)

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_distinct_property_values(self, model):
        queryset = model.objects.select_properties('version').values('version').distinct()
        assert queryset.count() == len(queryset) == 4
        assert set(obj_dict['version'] for obj_dict in queryset) == {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}

    @pytest.mark.parametrize('model, filters, expected_versions', [
        (VersionWithClassBasedProperties, {}, {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (VersionWithClassBasedProperties, {'patch': 0}, {'1.3.0', '2.0.0'}),
        (VersionWithClassBasedProperties, {'major_minor': '1.3'}, {'1.3.0', '1.3.1'}),
        (VersionWithClassBasedProperties, {'version': '2.0.0'}, {'2.0.0'}),
        (VersionWithDecoratorBasedProperties, {}, {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (VersionWithDecoratorBasedProperties, {'patch': 0}, {'1.3.0', '2.0.0'}),
        (VersionWithDecoratorBasedProperties, {'major_minor': '1.3'}, {'1.3.0', '1.3.1'}),
        (VersionWithDecoratorBasedProperties, {'version': '2.0.0'}, {'2.0.0'}),
    ])
    def test_values_list(self, model, filters, expected_versions):
        queryset = model.objects.filter(**filters).select_properties('version').values_list('version', flat=True)
        assert set(queryset) == expected_versions
