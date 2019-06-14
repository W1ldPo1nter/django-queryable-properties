# encoding: utf-8

import pytest

from django import VERSION as DJANGO_VERSION

from ..models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                      CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties,
                      VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class TestAggregateAnnotations(object):

    @pytest.mark.parametrize('model, filters, expected_version_counts', [
        (ApplicationWithClassBasedProperties, {}, {3, 4}),
        (ApplicationWithClassBasedProperties, {'version_count__gt': 3}, {4}),
        (ApplicationWithClassBasedProperties, {'version_count': 5}, {}),
        (ApplicationWithDecoratorBasedProperties, {}, {3, 4}),
        (ApplicationWithDecoratorBasedProperties, {'version_count__gt': 3}, {4}),
        (ApplicationWithDecoratorBasedProperties, {'version_count': 5}, {}),
    ])
    def test_values_to_limit_fields(self, model, filters, expected_version_counts):
        # Delete one version to create separate version counts
        model.objects.all()[0].versions.all()[0].delete()
        queryset = model.objects.filter(**filters).select_properties('version_count').values('version_count')
        assert all(obj_dict['version_count'] in expected_version_counts for obj_dict in queryset)

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_values_for_custom_grouping(self, model):
        values = model.objects.values('common_data').select_properties('version_count')
        assert len(values) == 1
        assert values[0]['version_count'] == 8

    @pytest.mark.parametrize('model', [CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties])
    def test_values_for_custom_grouping_across_relation(self, model):
        queryset = model.objects.values('pk', 'applications__pk').filter(applications__version_count=4)
        assert len(queryset) == 3
        assert len(set((obj_dict['pk'], obj_dict['applications__pk']) for obj_dict in queryset)) == 3

    @pytest.mark.parametrize('model, filters, expected_version_counts', [
        (ApplicationWithClassBasedProperties, {}, {3, 4}),
        (ApplicationWithClassBasedProperties, {'version_count__gt': 3}, {4}),
        (ApplicationWithClassBasedProperties, {'version_count': 5}, {}),
        (ApplicationWithDecoratorBasedProperties, {}, {3, 4}),
        (ApplicationWithDecoratorBasedProperties, {'version_count__gt': 3}, {4}),
        (ApplicationWithDecoratorBasedProperties, {'version_count': 5}, {}),
    ])
    def test_values_list(self, model, filters, expected_version_counts):
        queryset = model.objects.filter(**filters).select_properties('version_count').values_list('version_count',
                                                                                                  flat=True)
        assert all(version_count in expected_version_counts for version_count in queryset)


@pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
class TestExpressionAnnotations(object):

    @pytest.mark.parametrize('model, filters, expected_versions', [
        (VersionWithClassBasedProperties, {}, {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (VersionWithClassBasedProperties, {'major_minor': '1.3'}, {'1.3.0', '1.3.1'}),
        (VersionWithClassBasedProperties, {'version': '2.0.0'}, {'2.0.0'}),
        (VersionWithDecoratorBasedProperties, {}, {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (VersionWithDecoratorBasedProperties, {'major_minor': '1.3'}, {'1.3.0', '1.3.1'}),
        (VersionWithDecoratorBasedProperties, {'version': '2.0.0'}, {'2.0.0'}),
    ])
    def test_values_after_annotate(self, model, filters, expected_versions):
        queryset = model.objects.filter(**filters).select_properties('version').values('version')
        assert all(obj_dict['version'] in expected_versions for obj_dict in queryset)

    @pytest.mark.parametrize('model, filters, expected_versions', [
        (VersionWithClassBasedProperties, {}, {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (VersionWithClassBasedProperties, {'major_minor': '1.3'}, {'1.3.0', '1.3.1'}),
        (VersionWithClassBasedProperties, {'version': '2.0.0'}, {'2.0.0'}),
        (VersionWithDecoratorBasedProperties, {}, {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (VersionWithDecoratorBasedProperties, {'major_minor': '1.3'}, {'1.3.0', '1.3.1'}),
        (VersionWithDecoratorBasedProperties, {'version': '2.0.0'}, {'2.0.0'}),
    ])
    def test_values_list(self, model, filters, expected_versions):
        queryset = model.objects.filter(**filters).select_properties('version').values_list('version', flat=True)
        assert all(version in expected_versions for version in queryset)
