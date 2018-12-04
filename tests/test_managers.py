# encoding: utf-8
import pytest

from django import VERSION as DJANGO_VERSION
from django.core.exceptions import FieldError
from django.db import models
try:
    from django.db.models.functions import Concat
except ImportError:
    Concat = []  # This way, the name can be used in "and" expressions in parametrizations
from django.utils import six

from queryable_properties.exceptions import QueryablePropertyError

from .models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                     VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)


@pytest.mark.django_db
class TestQueryFilters(object):

    @pytest.mark.parametrize('model, major_minor, expected_count', [
        (VersionWithClassBasedProperties, '1.2', 2),
        (VersionWithClassBasedProperties, '1.3', 4),
        (VersionWithClassBasedProperties, '2.0', 2),
        (VersionWithDecoratorBasedProperties, '1.2', 2),
        (VersionWithDecoratorBasedProperties, '1.3', 4),
        (VersionWithDecoratorBasedProperties, '2.0', 2),
    ])
    def test_simple_filter(self, versions, model, major_minor, expected_count):
        # Also test that using non-property filters still work and can be used
        # together with filters for queryable properties
        queryset = model.objects.filter(major_minor=major_minor, major=major_minor[0])
        assert len(queryset) == expected_count
        assert all(obj.major_minor == major_minor for obj in queryset)

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_filter_without_required_annotation(self, versions, model):
        # Filtering the 'version' property is also based on filtering the
        # 'major_minor' property, so this test also tests properties that build
        # on each other
        queryset = model.objects.filter(version='1.2.3')
        assert 'version' not in queryset.query.annotations
        assert all(obj.version == '1.2.3' for obj in queryset)

    @pytest.mark.skipif(DJANGO_VERSION < (1, 9), reason='using MIN/MAX in filters was not supported with sqlite')
    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_filter_with_required_annotation(self, versions, model):
        version_model = model.objects.first().versions.model
        version_model.objects.filter(version='2.0.0')[0].delete()
        queryset = model.objects.filter(highest_version='2.0.0')
        assert 'highest_version' in queryset.query.annotations
        assert len(queryset) == 1
        application = queryset[0]
        assert application.versions.filter(major=2, minor=0, patch=0).exists()
        # Check that a property annotation used implicitly by a filter does not
        # lead to a selection of the property annotation
        assert not model.highest_version._has_cached_value(application)

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_filter_implementation_used_despite_present_annotation(self, versions, model):
        queryset = model.objects.select_properties('version').filter(version='2.0.0')
        pseudo_sql = six.text_type(queryset.query)
        assert '"major" = 2' in pseudo_sql
        assert '"minor" = 0' in pseudo_sql
        assert '"patch" = 0' in pseudo_sql
        assert queryset.count() == 2

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_exception_on_unimplemented_filter(self, monkeypatch, model):
        monkeypatch.setattr(model.version, 'get_filter', None)
        with pytest.raises(QueryablePropertyError):
            model.objects.filter(version='1.2.3')

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_standard_exception_on_invalid_field_name(self, model):
        with pytest.raises(FieldError):
            model.objects.filter(non_existent_field=1337)

    @pytest.mark.skipif(DJANGO_VERSION < (1, 9), reason="type check didn't exist before Django 1.9")
    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_standard_exception_on_invalid_filter_expression(self, model):
        with pytest.raises(FieldError):
            # The dict is passed as arg instead of kwargs, making it an invalid
            # filter expression.
            model.objects.filter(models.Q({'version': '2.0.0'}))


@pytest.mark.django_db
class TestNonModelInstanceQueries(object):

    @pytest.mark.parametrize('model, filters, expected_versions', [
        (VersionWithClassBasedProperties, {}, {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (VersionWithClassBasedProperties, {'major_minor': '1.3'}, {'1.3.0', '1.3.1'}),
        (VersionWithClassBasedProperties, {'version': '2.0.0'}, {'2.0.0'}),
        (VersionWithDecoratorBasedProperties, {}, {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (VersionWithDecoratorBasedProperties, {'major_minor': '1.3'}, {'1.3.0', '1.3.1'}),
        (VersionWithDecoratorBasedProperties, {'version': '2.0.0'}, {'2.0.0'}),
    ])
    def test_values(self, versions, model, filters, expected_versions):
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
    def test_values_list(self, versions, model, filters, expected_versions):
        queryset = model.objects.filter(**filters).select_properties('version').values_list('version', flat=True)
        assert all(version in expected_versions for version in queryset)


@pytest.mark.django_db
class TestQueryAnnotations(object):

    @pytest.mark.parametrize('model, filters', [
        (VersionWithClassBasedProperties, {}),
        (VersionWithDecoratorBasedProperties, {}),
        (VersionWithClassBasedProperties, {'version': '1.2.3'}),
        (VersionWithDecoratorBasedProperties, {'version': '1.2.3'}),
    ])
    def test_cached_annotation_value(self, versions, model, filters):
        # Filter both before and after the select_properties call to check if
        # the annotation gets selected correctly regardless
        queryset = model.objects.filter(**filters).select_properties('version').filter(**filters)
        assert 'version' in queryset.query.annotations
        assert all(model.version._has_cached_value(obj) for obj in queryset)

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_cached_annotation_value_with_group_by(self, versions, model):
        queryset = model.objects.select_properties('version_count')
        assert 'version_count' in queryset.query.annotations
        assert all(model.version_count._has_cached_value(obj) for obj in queryset)

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason='F objects could not be used as annotations before Django 1.8')
    @pytest.mark.parametrize('model, annotation, expected_value', [
        (VersionWithClassBasedProperties, models.F('version'), '{}'),
        (VersionWithDecoratorBasedProperties, models.F('version'), '{}'),
    ] + (Concat and [  # The next test parametrizations are only active if Concat is defined
        (VersionWithClassBasedProperties, Concat(models.Value('V'), 'version'), 'V{}'),
        (VersionWithDecoratorBasedProperties, Concat(models.Value('V'), 'version'), 'V{}'),
    ]))
    def test_annotation_based_on_queryable_property(self, versions, model, annotation, expected_value):
        queryset = model.objects.annotate(annotation=annotation)
        for version in queryset:
            assert version.annotation == expected_value.format(version.version)
            # Check that a property annotation used implicitly by another
            # annotation does not lead to a selection of the property
            # annotation
            assert not model.version._has_cached_value(version)

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_exception_on_unimplemented_annotater(self, model):
        with pytest.raises(QueryablePropertyError):
            model.objects.select_properties('major_minor')


@pytest.mark.django_db
class TestUpdateQueries(object):

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_simple_update(self, versions, model):
        queryset = model.objects.filter(major_minor='2.0')
        pks = list(queryset.values_list('pk', flat=True))
        assert queryset.update(major_minor='42.42') == len(pks)
        for pk in pks:
            version = model.objects.get(pk=pk)  # Reload from DB
            assert version.major_minor == '42.42'

    @pytest.mark.parametrize('model, update_kwargs', [
        (VersionWithClassBasedProperties, {'version': '1.3.37'}),
        (VersionWithDecoratorBasedProperties, {'version': '1.3.37'}),
        # Also test that setting the same field(s) via multiple queryable
        # properties works as long as they try to set the same values
        (VersionWithClassBasedProperties, {'version': '1.3.37', 'major_minor': '1.3'}),
        (VersionWithDecoratorBasedProperties, {'version': '1.3.37', 'major_minor': '1.3'}),
    ])
    def test_update_based_on_other_property(self, versions, model, update_kwargs):
        queryset = model.objects.filter(version='1.3.1')
        pks = list(queryset.values_list('pk', flat=True))
        assert queryset.update(**update_kwargs) == len(pks)
        for pk in pks:
            version = model.objects.get(pk=pk)  # Reload from DB
            assert version.version == update_kwargs['version']

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_exception_on_unimplemented_updater(self, model):
        with pytest.raises(QueryablePropertyError):
            model.objects.update(highest_version='1.3.37')

    @pytest.mark.parametrize('model, kwargs', [
        (VersionWithClassBasedProperties, {'major_minor': '42.42', 'major': 18}),
        (VersionWithClassBasedProperties, {'major_minor': '1.2', 'version': '1.3.37', 'minor': 5}),
        (VersionWithDecoratorBasedProperties, {'major_minor': '42.42', 'major': 18}),
        (VersionWithDecoratorBasedProperties, {'major_minor': '1.2', 'version': '1.3.37', 'minor': 5}),
    ])
    def test_exception_on_conflicting_values(self, model, kwargs):
        with pytest.raises(QueryablePropertyError):
            model.objects.update(**kwargs)


@pytest.mark.django_db
class TestOrdering(object):

    @pytest.mark.parametrize('model, order_by, reverse, with_selection', [
        # All parametrizations are expected to yield results ordered by the
        # full version (ASC/DESC depending on the reverse parameter).
        (VersionWithClassBasedProperties, 'version', False, False),
        (VersionWithDecoratorBasedProperties, 'version', False, False),
        (VersionWithClassBasedProperties, 'version', False, True),
        (VersionWithDecoratorBasedProperties, 'version', False, True),
        (VersionWithClassBasedProperties, '-version', True, False),
        (VersionWithDecoratorBasedProperties, '-version', True, False),
        (VersionWithClassBasedProperties, '-version', True, True),
        (VersionWithDecoratorBasedProperties, '-version', True, True),
    ] + (Concat and [  # The next test parametrizations are only active if Concat is defined
        (VersionWithClassBasedProperties, Concat(models.Value('V'), 'version').asc(), False, False),
        (VersionWithDecoratorBasedProperties, Concat(models.Value('V'), 'version').asc(), False, False),
        (VersionWithClassBasedProperties, Concat(models.Value('V'), 'version').asc(), False, True),
        (VersionWithDecoratorBasedProperties, Concat(models.Value('V'), 'version').asc(), False, True),
        (VersionWithClassBasedProperties, Concat(models.Value('V'), 'version').desc(), True, False),
        (VersionWithDecoratorBasedProperties, Concat(models.Value('V'), 'version').desc(), True, False),
        (VersionWithClassBasedProperties, Concat(models.Value('V'), 'version').desc(), True, True),
        (VersionWithDecoratorBasedProperties, Concat(models.Value('V'), 'version').desc(), True, True),
    ]))
    def test_order_by_property_with_annotater(self, model, order_by, reverse, with_selection, versions):
        queryset = model.objects.all()
        if with_selection:
            queryset = queryset.select_properties('version')
        results = list(queryset.order_by(order_by))
        assert results == sorted(results, key=lambda version: version.version, reverse=reverse)
        # Check that ordering by a property annotation does not lead to a
        # selection of the property annotation
        assert all(model.version._has_cached_value(version) is with_selection for version in results)

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_exception_on_unimplemented_annotater(self, model):
        with pytest.raises(QueryablePropertyError):
            iter(model.objects.order_by('major_minor'))
