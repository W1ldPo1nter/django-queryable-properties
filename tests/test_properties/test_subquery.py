# -*- coding: utf-8 -*-
import pytest
import six
from django import VERSION as DJANGO_VERSION
from django.db import models

from queryable_properties.properties import QueryableProperty, SubqueryExistenceCheckProperty, SubqueryFieldProperty
from queryable_properties.utils import get_queryable_property
from queryable_properties.utils.internal import get_queryable_property_descriptor
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
        },
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
        },
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

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('field_name, value, expected_properties, expect_v2_match', [
        ('highest_version_object', 'pk', {'highest_version_object'}, True),
        ('highest_version_object', 'obj', {'highest_version_object'}, True),
        ('highest_version_object__gt', 'pk', {'highest_version_object'}, False),
        ('highest_version_object__pk', 'pk', {'highest_version_object'}, True),
        ('highest_version_object__pk', 'obj', {'highest_version_object'}, True),
        ('highest_version_object__pk__gt', 'obj', {'highest_version_object'}, False),
        ('highest_version_object__id', 'pk', {'highest_version_object'}, True),
        ('highest_version_object__id', 'obj', {'highest_version_object'}, True),
        ('highest_version_object__id__gt', 'obj', {'highest_version_object'}, False),
        ('highest_version_object__application', 'application_id',
         {'highest_version_object', 'highest_version_object-application_id'}, True),
        ('highest_version_object__application_id', 'application_id',
         {'highest_version_object', 'highest_version_object-application_id'}, True),
        ('highest_version_object__major', 2, {'highest_version_object', 'highest_version_object-major'}, True),
        ('highest_version_object__major__gt', 1, {'highest_version_object', 'highest_version_object-major'}, True),
        ('highest_version_object__major', 1, {'highest_version_object', 'highest_version_object-major'}, False),
        ('highest_version_object__major__lt', 2, {'highest_version_object', 'highest_version_object-major'}, False),
    ])
    def test_filter(self, categories, applications, field_name, value, expected_properties, expect_v2_match):
        applications[1].versions.filter(major=2).delete()
        expected_apps = {applications[int(not expect_v2_match)]}
        expected_categories = {categories[0]} if expect_v2_match else set(categories[:2])
        if value in ('pk', 'application_id'):
            value = applications[0].versions.values_list(value, flat=True).get(major=2)
        elif value == 'obj':
            value = applications[0].versions.get(major=2)

        for queryset, expected_results in (
            (ApplicationWithClassBasedProperties.objects.filter(**{field_name: value}), expected_apps),
            (
                CategoryWithClassBasedProperties.objects.filter(**{'applications__{}'.format(field_name): value}),
                expected_categories,
            ),
        ):
            assert {ref.property.name for ref in queryset.query._queryable_property_annotations} == expected_properties
            assert set(queryset) == expected_results

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('select, expected_properties', [
        (('highest_version_object',), None),
        (
            ('highest_version_object__major', 'highest_version_object__minor'),
            {'highest_version_object-major', 'highest_version_object-minor'},
        ),
        (('highest_version_object__pk',), {'highest_version_object'}),
        (('highest_version_object__id',), {'highest_version_object'}),
        (('highest_version_object__major', 'highest_version_object'), None),
    ])
    def test_annotation_select(self, django_assert_num_queries, applications, ref, select, expected_properties):
        version = VersionWithClassBasedProperties.objects.filter(major=2)[0]
        if not expected_properties:
            expected_properties = {sub_ref.property.name for sub_ref in
                                   six.itervalues(ref.property._field_property_refs)}
            expected_properties.add(ref.property.name)
        queryset = ApplicationWithClassBasedProperties.objects.select_properties(*select)

        assert {r.property.name for r in queryset.query._queryable_property_annotations} == expected_properties
        with django_assert_num_queries(1):
            for application in queryset:
                if 'highest_version_object' in expected_properties:
                    assert ref.descriptor.has_cached_value(application)
                expected_properties.discard('highest_version_object')
                expected_properties.discard('highest_version_object-application_id')
                for name in expected_properties:
                    descriptor = get_queryable_property_descriptor(ApplicationWithClassBasedProperties, name)
                    assert descriptor.get_cached_value(application) == getattr(version, descriptor.prop.field_name)

    @pytest.mark.django_db
    @pytest.mark.parametrize('order_by, expected_property, expect_app2_first', [
        ('highest_version_object', 'highest_version_object', False),
        ('highest_version_object__pk', 'highest_version_object', False),
        ('highest_version_object__id', 'highest_version_object', False),
        ('highest_version_object__application', 'highest_version_object-application_id', False),
        ('highest_version_object__application_id', 'highest_version_object-application_id', False),
        ('highest_version_object__major', 'highest_version_object-major', True),
    ])
    def test_annotation_implicit(self, applications, versions, order_by, expected_property, expect_app2_first):
        versions[7].delete()
        expected_apps = [applications[1], applications[0]] if expect_app2_first else applications[:2]
        expected_versions = versions[:7]
        if expect_app2_first:
            while expected_versions[-1].application == expected_apps[0]:
                expected_versions.insert(0, expected_versions.pop())

        for queryset, expected_results in (
            (ApplicationWithClassBasedProperties.objects.order_by(order_by), expected_apps),
            (
                VersionWithClassBasedProperties.objects.order_by('application__{}'.format(order_by), 'pk'),
                expected_versions,
            ),
        ):
            assert {ref.property.name for ref in queryset.query._queryable_property_annotations} == {expected_property}
            assert list(queryset) == expected_results
