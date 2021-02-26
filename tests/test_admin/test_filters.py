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
    def test_initializer(self, admin_instance, query_path, expected_property):
        field = QueryablePropertyField(admin_instance, query_path)
        output_field = get_output_field(expected_property.get_annotation(expected_property.model))
        assert type(field.output_field) is type(output_field)  # Old django versions don't implement field comparison
        assert field.model_admin is admin_instance
        assert field.property is expected_property
        assert field.property_path == query_path
        assert field.null is getattr(output_field, 'null', True)
        assert field.empty_strings_allowed is getattr(output_field, 'null', True)

    @pytest.mark.parametrize('query_path', ['name', 'neither_field_nor_property', 'version_count__gt'])
    def test_initializer_error(self, admin_instance, query_path):
        with pytest.raises(QueryablePropertyError):
            QueryablePropertyField(admin_instance, query_path)

    def test_attribute_passthrough(self, admin_instance):
        field = QueryablePropertyField(admin_instance, 'version_count')
        assert field.model is ApplicationWithClassBasedProperties
        assert field.name == 'version_count'
        assert field.verbose_name == 'Version count'

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    def test_flatchoices_mapping_property(self):
        admin = VersionAdmin(VersionWithClassBasedProperties, site)
        field = QueryablePropertyField(admin, 'release_type_verbose_name')
        assert tuple(field.flatchoices) == (
            ('Alpha', 'Alpha'),
            ('Beta', 'Beta'),
            ('Stable', 'Stable'),
            (None, field.empty_value_display),
        )

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    def test_flatchoices_boolean_property(self, admin_instance):
        field = QueryablePropertyField(admin_instance, 'has_version_with_changelog')
        assert tuple(field.flatchoices) == ()

    @pytest.mark.django_db
    @pytest.mark.parametrize('query_path, expected_choices', [
        ('version_count', ((3, 3), (4, 4))),
        ('categories__version_count', ((4, 4), (7, 7))),
    ])
    def test_flatchoices_other_properties(self, versions, admin_instance, query_path, expected_choices):
        versions[0].delete()
        field = QueryablePropertyField(admin_instance, query_path)
        assert tuple(field.flatchoices) == expected_choices

    @pytest.mark.parametrize('filter_class, expected_filter_class', [
        (None, DateFieldListFilter),
        (ChoicesFieldListFilter, ChoicesFieldListFilter),
    ])
    def test_get_filter_creator(self, rf, admin_instance, filter_class, expected_filter_class):
        field = QueryablePropertyField(admin_instance, 'support_start_date')
        field.output_field = DateField(null=True)  # To set an output field for Django versions that don't support it
        creator = field.get_filter_creator(filter_class)
        assert callable(creator)
        list_filter = creator(rf.get('/'), {}, admin_instance.model, admin_instance)
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
    def test_get_class(self, prop, admin_class, expected_filter_class):
        field = QueryablePropertyField(admin_class(prop.model, site), prop.name)
        assert QueryablePropertyListFilter.get_class(field) is expected_filter_class
