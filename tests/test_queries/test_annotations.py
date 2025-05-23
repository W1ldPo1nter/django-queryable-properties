# encoding: utf-8

import pytest
from django import VERSION as DJANGO_VERSION
from django.db import connection, models

from queryable_properties.query import QUERYING_PROPERTIES_MARKER
from queryable_properties.utils.internal import get_queryable_property_descriptor
from ..app_management.models import (
    ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties, VersionWithClassBasedProperties,
    VersionWithDecoratorBasedProperties,
)
from ..conftest import Concat, Value
from ..marks import skip_if_no_alias, skip_if_no_expressions

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class TestAggregateAnnotations(object):

    @pytest.mark.parametrize('model, filters', [
        (ApplicationWithClassBasedProperties, {}),
        (ApplicationWithClassBasedProperties, {'version_count__gt': 3}),
        (ApplicationWithDecoratorBasedProperties, {}),
        (ApplicationWithDecoratorBasedProperties, {'version_count__gt': 3}),
    ])
    def test_cached_annotation_value(self, model, filters):
        # Filter both before and after the select_properties call to check if
        # the annotation gets selected correctly regardless
        queryset = model.objects.filter(**filters).select_properties('version_count', 'major_sum').filter(**filters)
        assert 'version_count' in queryset.query.annotations
        assert 'major_sum' in queryset.query.annotations
        for application in queryset:
            assert model.version_count.has_cached_value(application)
            assert application.version_count == 4
            assert model.major_sum.has_cached_value(application)
            assert application.major_sum == 5
            assert not hasattr(application, QUERYING_PROPERTIES_MARKER)

    @pytest.mark.parametrize('model, limit, expected_total', [
        (ApplicationWithClassBasedProperties, None, 8),
        (ApplicationWithClassBasedProperties, 1, 4),
        (ApplicationWithDecoratorBasedProperties, None, 8),
        (ApplicationWithDecoratorBasedProperties, 1, 4),
    ])
    def test_aggregate_based_on_queryable_property(self, model, limit, expected_total):
        result = model.objects.all()[:limit].aggregate(total_version_count=models.Sum('version_count'))
        assert result['total_version_count'] == expected_total

    @pytest.mark.parametrize('model, limit, expected_total', [
        (VersionWithClassBasedProperties, None, 32),
        (VersionWithClassBasedProperties, 4, 16),
        (VersionWithDecoratorBasedProperties, None, 32),
        (VersionWithDecoratorBasedProperties, 4, 16),
    ])
    def test_aggregate_based_on_queryable_property_across_relation(self, model, limit, expected_total):
        result = model.objects.all()[:limit].aggregate(total_version_count=models.Sum('application__version_count'))
        assert result['total_version_count'] == expected_total

    @skip_if_no_expressions
    @pytest.mark.parametrize('model, annotation', [
        (VersionWithClassBasedProperties, models.F('application__version_count')),
        (VersionWithDecoratorBasedProperties, models.F('application__version_count')),
    ])
    def test_annotation_based_on_queryable_property_across_relation(self, model, annotation):
        model.objects.all()[0].delete()
        queryset = model.objects.annotate(annotation=annotation)
        assert all(obj.annotation == obj.application.version_count for obj in queryset)

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_iterator(self, model):
        queryset = model.objects.filter(version_count=4).select_properties('version_count')
        for application in queryset.iterator():
            assert model.version_count.has_cached_value(application)
            assert application.version_count == 4
        assert queryset._result_cache is None

    @skip_if_no_alias
    @pytest.mark.parametrize('model, with_selection', [
        (ApplicationWithClassBasedProperties, False),
        (ApplicationWithClassBasedProperties, True),
        (ApplicationWithDecoratorBasedProperties, False),
        (ApplicationWithDecoratorBasedProperties, True),
    ])
    def test_alias(self, model, with_selection):
        queryset = model.objects.alias(alias=models.F('version_count') + 1)
        if with_selection:
            queryset = queryset.select_properties('version_count')
        results = list(queryset.filter(alias=5))
        assert len(results) == 2
        for application in results:
            assert model.version_count.has_cached_value(application) is with_selection
            assert application.version_count == 4

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_removed_annotation(self, model):
        """
        Test that queries can still be performed even if queryable property
        annotations have been manually removed from the queryset.
        """
        queryset = model.objects.select_properties('version_count')
        del queryset.query.annotations['version_count']
        assert bool(queryset)
        assert all(not model.version_count.has_cached_value(obj) for obj in queryset)

    @pytest.mark.skipif(DJANGO_VERSION < (1, 7), reason="Raw queries didn't exist before Django 1.7")
    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_raw_query(self, model):
        pks, names = zip(*model.objects.values_list('pk', 'name'))
        queryset = model.objects.raw('SELECT id, name, 5 AS version_count FROM {}'.format(model._meta.db_table))
        counter = 0
        for application in queryset:
            assert model.version_count.has_cached_value(application) is True
            assert application.version_count == 5
            assert application.pk in pks
            assert application.name in names
            assert not hasattr(application, QUERYING_PROPERTIES_MARKER)
            counter += 1
        assert counter == 2


@skip_if_no_expressions
class TestExpressionAnnotations(object):

    @pytest.mark.parametrize('model, filters', [
        (VersionWithClassBasedProperties, {}),
        (VersionWithDecoratorBasedProperties, {}),
        (VersionWithClassBasedProperties, {'version': '1.2.3'}),
        (VersionWithDecoratorBasedProperties, {'version': '1.2.3'}),
    ])
    def test_cached_annotation_value(self, model, filters):
        # Filter both before and after the select_properties call to check if
        # the annotation gets selected correctly regardless
        queryset = model.objects.filter(**filters).select_properties('version').filter(**filters)
        assert 'version' in queryset.query.annotations
        assert all(model.version.has_cached_value(obj) for obj in queryset)

    @pytest.mark.parametrize('model, property_name, annotation, expected_count, record_checker', [
        (VersionWithClassBasedProperties, 'version', models.F('version'), 8,
         lambda obj: obj.annotation == obj.version),
        (VersionWithDecoratorBasedProperties, 'version', models.F('version'), 8,
         lambda obj: obj.annotation == obj.version),
        (VersionWithClassBasedProperties, 'version', Concat(Value('V'), 'version'), 8,
         lambda obj: obj.annotation == 'V' + obj.version),
        (VersionWithDecoratorBasedProperties, 'version', Concat(Value('V'), 'version'), 8,
         lambda obj: obj.annotation == 'V' + obj.version),
        (ApplicationWithClassBasedProperties, 'versions__version', models.F('versions__version'), 8,
         lambda obj: obj.annotation in ('1.2.3', '1.3.0', '1.3.1', '2.0.0')),
        (ApplicationWithDecoratorBasedProperties, 'versions__version', models.F('versions__version'), 8,
         lambda obj: obj.annotation in ('1.2.3', '1.3.0', '1.3.1', '2.0.0')),
        (ApplicationWithClassBasedProperties, 'versions__version', Concat(Value('V'), 'versions__version'), 8,
         lambda obj: obj.annotation in ('V1.2.3', 'V1.3.0', 'V1.3.1', 'V2.0.0')),
        (ApplicationWithDecoratorBasedProperties, 'versions__version', Concat(Value('V'), 'versions__version'), 8,
         lambda obj: obj.annotation in ('V1.2.3', 'V1.3.0', 'V1.3.1', 'V2.0.0')),
    ])
    def test_annotation_based_on_queryable_property(self, model, property_name, annotation, expected_count,
                                                    record_checker):
        queryset = model.objects.annotate(annotation=annotation)
        assert queryset.count() == len(queryset) == expected_count
        assert all(record_checker(obj) for obj in queryset)
        if '__' not in property_name:
            # Check that a property annotation used implicitly by another
            # annotation does not lead to a selection of the property
            # annotation
            descriptor = get_queryable_property_descriptor(model, property_name)
            assert all(not descriptor.has_cached_value(obj) for obj in queryset)

    @skip_if_no_alias
    @pytest.mark.parametrize('model, with_selection', [
        (VersionWithClassBasedProperties, False),
        (VersionWithClassBasedProperties, True),
        (VersionWithDecoratorBasedProperties, False),
        (VersionWithDecoratorBasedProperties, True),
    ])
    def test_alias(self, model, with_selection):
        queryset = model.objects.alias(alias=Concat(Value('V'), 'version'))
        if with_selection:
            queryset = queryset.select_properties('version')
        results = list(queryset.filter(alias='V2.0.0'))
        assert len(results) == 2
        for version in results:
            assert model.version.has_cached_value(version) is with_selection
            assert version.version == '2.0.0'

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_iterator(self, model):
        queryset = model.objects.filter(major_minor='2.0').select_properties('version')
        for version in queryset.iterator():
            assert model.version.has_cached_value(version)
            assert version.version == '2.0.0'
        assert queryset._result_cache is None

    @pytest.mark.skipif(DJANGO_VERSION < (4, 2), reason='Sliced prefetches were introduced in Django 4.2')
    def test_sliced_prefetch(self):
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as context:
            versions = VersionWithClassBasedProperties.objects.select_properties('released_in_2018').order_by(
                'major', 'minor', 'patch')
            apps = ApplicationWithClassBasedProperties.objects.prefetch_related(
                models.Prefetch('versions', versions[1:3], to_attr='prefetched_versions'))
            for app in apps:
                assert all(version.major_minor == '1.3' for version in app.prefetched_versions)
            assert context.captured_queries[1]['sql'].count('"released_in_2018"') == 2
