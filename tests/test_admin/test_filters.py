# -*- coding: utf-8 -*-

import pytest
from django import VERSION as DJANGO_VERSION
from django.contrib.admin import site
from django.contrib.admin.filters import BooleanFieldListFilter, ChoicesFieldListFilter, DateFieldListFilter
from django.db.models import DateField

from queryable_properties.admin.filters import QueryablePropertyField, QueryablePropertyListFilter
from queryable_properties.exceptions import QueryablePropertyError
from queryable_properties.utils.internal import get_output_field
from ..app_management.admin import ApplicationAdmin, VersionAdmin
from ..app_management.models import (ApplicationWithClassBasedProperties, CategoryWithClassBasedProperties,
                                     VersionWithClassBasedProperties)


class TestQueryablePropertyField(object):

    @pytest.fixture
    def admin_instance(self):
        return ApplicationAdmin(ApplicationWithClassBasedProperties, site)

    @pytest.mark.parametrize('query_path, expected_property', [
        ('version_count', ApplicationWithClassBasedProperties.version_count),
        ('categories__version_count', CategoryWithClassBasedProperties.version_count),
    ])
    def test_initializer(self, rf, admin_instance, query_path, expected_property):
        request = rf.get('/')
        field = QueryablePropertyField(admin_instance, request, query_path)
        output_field = get_output_field(expected_property.get_annotation(expected_property.model))
        assert field.output_field == output_field
        assert field.model_admin is admin_instance
        assert field.request is request
        assert field.property is expected_property
        assert field.property_path == query_path
        assert field.null is getattr(output_field, 'null', True)
        assert field.empty_strings_allowed is getattr(output_field, 'null', True)

    @pytest.mark.parametrize('query_path', ['name', 'neither_field_nor_property', 'version_count__gt'])
    def test_initializer_error(self, rf, admin_instance, query_path):
        with pytest.raises(QueryablePropertyError):
            QueryablePropertyField(admin_instance, rf.get('/'), query_path)

    def test_attribute_passthrough(self, rf, admin_instance):
        field = QueryablePropertyField(admin_instance, rf.get('/'), 'version_count')
        assert field.model is ApplicationWithClassBasedProperties
        assert field.name == 'version_count'
        assert field.verbose_name == 'Version count'

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    def test_flatchoices_mapping_property(self, rf):
        admin = VersionAdmin(VersionWithClassBasedProperties, site)
        field = QueryablePropertyField(admin, rf.get('/'), 'release_type_verbose_name')
        assert tuple(field.flatchoices) == (
            ('Alpha', 'Alpha'),
            ('Beta', 'Beta'),
            ('Stable', 'Stable'),
            (None, admin.get_empty_value_display()),
        )

    def test_flatchoices_boolean_property(self, admin_instance, rf):
        field = QueryablePropertyField(admin_instance, rf.get('/'), 'has_version_with_changelog')
        assert tuple(field.flatchoices) == ()

    @pytest.mark.django_db
    def test_flatchoices_other_properties(self, versions, admin_instance, rf):
        versions[0].delete()
        field = QueryablePropertyField(admin_instance, rf.get('/'), 'version_count')
        assert tuple(field.flatchoices) == (
            (3, 3),
            (4, 4),
        )

    @pytest.mark.parametrize('filter_class, expected_filter_class', [
        (None, DateFieldListFilter),
        (ChoicesFieldListFilter, ChoicesFieldListFilter),
    ])
    def test_get_filter_creator(self, rf, admin_instance, filter_class, expected_filter_class):
        request = rf.get('/')
        field = QueryablePropertyField(admin_instance, request, 'support_start_date')
        field.output_field = DateField(null=True)  # To set an output field for Django versions that don't support it
        creator = field.get_filter_creator(filter_class)
        assert callable(creator)
        list_filter = creator(request, {}, admin_instance.model, admin_instance)
        assert isinstance(list_filter, expected_filter_class)
        assert list_filter.field is field
        assert list_filter.field_path == field.property_path


class TestQueryablePropertyListFilter(object):

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="output fields couldn't be declared before Django 1.8")
    @pytest.mark.parametrize('prop, admin_class, expected_filter_class', [
        (ApplicationWithClassBasedProperties.has_version_with_changelog, ApplicationAdmin, BooleanFieldListFilter),
        (VersionWithClassBasedProperties.release_type_verbose_name, VersionAdmin, ChoicesFieldListFilter),
        (ApplicationWithClassBasedProperties.support_start_date, VersionAdmin, DateFieldListFilter),
        (VersionWithClassBasedProperties.version, VersionAdmin, ChoicesFieldListFilter),
    ])
    def test_get_class(self, rf, prop, admin_class, expected_filter_class):
        field = QueryablePropertyField(admin_class(prop.model, site), rf.get('/'), prop.name)
        assert QueryablePropertyListFilter.get_class(field) is expected_filter_class
