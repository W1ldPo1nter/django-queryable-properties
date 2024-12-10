# -*- coding: utf-8 -*-
import pytest
import six
from django import VERSION as DJANGO_VERSION
from django.db import models

from queryable_properties.properties import QueryableProperty, SubqueryExistenceCheckProperty, SubqueryFieldProperty
from queryable_properties.utils import get_queryable_property
from ..app_management.models import (
    ApplicationWithClassBasedProperties, CategoryWithClassBasedProperties, VersionWithClassBasedProperties,
)

pytestmark = [
    pytest.mark.skipif(DJANGO_VERSION < (1, 11), reason="Explicit subqueries didn't exist before Django 1.11")
]


class TestSubqueryFieldProperty(object):

    @pytest.mark.parametrize('kwargs', [
        {
            'queryset': ApplicationWithClassBasedProperties.objects.filter(name='test'),
            'field_name': 'name',
        },
        {
            'queryset': ApplicationWithClassBasedProperties.objects.all(),
            'field_name': 'common_data',
            'output_field': models.IntegerField(),
            'cached': True,
        }
    ])
    def test_initializer(self, kwargs):
        prop = SubqueryFieldProperty(**kwargs)
        assert prop.queryset is kwargs['queryset']
        assert prop.field_name == kwargs['field_name']
        assert prop.output_field is kwargs.get('output_field')
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('field_name, expected_value', [
        ('version', '2.0.0'),
        ('major', 2),
    ])
    def test_build_subquery(self, monkeypatch, applications, field_name, expected_value):
        prop = get_queryable_property(ApplicationWithClassBasedProperties, 'highest_version')
        monkeypatch.setattr(prop, 'field_name', field_name)
        assert applications[0].highest_version == expected_value


class TestSubqueryExistenceCheckProperty(object):

    @pytest.mark.parametrize('kwargs', [
        {
            'queryset': ApplicationWithClassBasedProperties.objects.filter(name='test'),
        },
        {
            'queryset': ApplicationWithClassBasedProperties.objects.all(),
            'negated': True,
            'cached': True,
        }
    ])
    def test_initializer(self, kwargs):
        prop = SubqueryExistenceCheckProperty(**kwargs)
        assert prop.queryset is kwargs['queryset']
        assert prop.negated == kwargs.get('negated', False)
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('negated, delete_v2, expected_result', [
        (False, False, True),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ])
    def test_build_subquery(self, monkeypatch, categories, negated, delete_v2, expected_result):
        if delete_v2:
            VersionWithClassBasedProperties.objects.filter(major=2).delete()
        prop = get_queryable_property(CategoryWithClassBasedProperties, 'has_v2')
        monkeypatch.setattr(prop, 'negated', negated)
        assert categories[0].has_v2 is expected_result


class TestSubqueryObjectProperty(object):  # TODO: test initializer, _build_sub_properties

    @pytest.fixture
    def ref(self):
        return get_queryable_property(ApplicationWithClassBasedProperties, 'highest_version_object')._get_ref()

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    def test_getter_no_cache(self, django_assert_num_queries, applications, ref):
        application = applications[0]
        version = application.versions.get(major=2)

        assert not ref.descriptor.has_cached_value(application)
        for sub_ref in six.itervalues(ref.property._field_property_refs):
            assert not sub_ref.descriptor.has_cached_value(application)

        with django_assert_num_queries(1):
            assert application.highest_version_object == version
            assert ref.descriptor.get_cached_value(application) == version
            for field in VersionWithClassBasedProperties._meta.concrete_fields:
                assert getattr(version, field.attname) == getattr(application.highest_version_object, field.attname)
            for name, sub_ref in six.iteritems(ref.property._field_property_refs):
                assert sub_ref.descriptor.get_cached_value(application) == getattr(version, name)

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('cached_fields', [
        set(),
        {'major', 'minor', 'patch', 'application_id'},
    ])
    def test_cached_raw_values(self, django_assert_num_queries, applications, ref, cached_fields):
        application = applications[0]
        version = application.versions.get(major=2)
        ref.descriptor.set_cached_value(application, version.pk)
        for name in cached_fields:
            ref.property._field_property_refs[name].descriptor.set_cached_value(application, getattr(version, name))

        with django_assert_num_queries(0):
            assert application.highest_version_object == version
            assert ref.descriptor.get_cached_value(application) == version
            for name in cached_fields:
                assert getattr(application.highest_version_object, name) == getattr(version, name)
            deferred_fields = set(field.attname for field in VersionWithClassBasedProperties._meta.concrete_fields)
            deferred_fields.discard(VersionWithClassBasedProperties._meta.pk.attname)
            deferred_fields.difference_update(cached_fields)
            assert application.highest_version_object.get_deferred_fields() == deferred_fields

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    def test_getter_cached_instance(self, django_assert_num_queries, applications, ref):
        application = applications[0]
        version = application.versions.get(major=2)
        ref.descriptor.set_cached_value(application, version)

        with django_assert_num_queries(0):
            assert application.highest_version_object is version
