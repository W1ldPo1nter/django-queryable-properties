# -*- coding: utf-8 -*-

import pytest
import six
from django import VERSION as DJANGO_VERSION
from django.contrib.admin import ModelAdmin, SimpleListFilter, site
from django.contrib.admin.filters import AllValuesFieldListFilter
from django.core.exceptions import ImproperlyConfigured

from queryable_properties.compat import admin_validation
from ..app_management.admin import ApplicationWithClassBasedPropertiesAdmin, VersionWithClassBasedPropertiesAdmin
from ..app_management.models import ApplicationWithClassBasedProperties, VersionWithClassBasedProperties


class Dummy(object):
    pass


class DummyListFilter(SimpleListFilter):
    parameter_name = 'dummy'


def assert_admin_validation(admin_class, model, error_id=None, exception_text=None):
    if hasattr(ModelAdmin, 'check'):
        if DJANGO_VERSION >= (1, 9):
            errors = admin_class(model, site).check()
        else:
            errors = admin_class.check(model)
        if error_id is None:
            assert not errors
        else:
            assert any(error.id == error_id for error in errors)

    if hasattr(admin_validation or ModelAdmin, 'validate'):
        try:
            if hasattr(ModelAdmin, 'validate'):
                admin_class.validate(model)
            else:
                admin_validation.validate(admin_class, model)
        except ImproperlyConfigured as e:
            assert exception_text is not None
            assert exception_text in six.text_type(e)
        else:
            assert exception_text is None


class TestQueryablePropertiesChecksMixin(object):

    @pytest.mark.parametrize('admin, model', [
        (VersionWithClassBasedPropertiesAdmin, VersionWithClassBasedProperties),
        (ApplicationWithClassBasedPropertiesAdmin, ApplicationWithClassBasedProperties),
    ])
    def test_admin_success(self, admin, model):
        assert_admin_validation(admin, model)

    def test_admin_date_hierarchy_non_annotatable_property(self, monkeypatch):
        monkeypatch.setattr(VersionWithClassBasedPropertiesAdmin, 'date_hierarchy', 'major_minor')
        assert_admin_validation(VersionWithClassBasedPropertiesAdmin, VersionWithClassBasedProperties,
                                'queryable_properties.admin.E002', '(queryable_properties.admin.E002)')

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="output fields couldn't be declared before Django 1.8")
    def test_admin_date_hierarchy_invalid_type(self, monkeypatch):
        monkeypatch.setattr(ApplicationWithClassBasedPropertiesAdmin, 'date_hierarchy', 'has_version_with_changelog')
        assert_admin_validation(ApplicationWithClassBasedPropertiesAdmin, ApplicationWithClassBasedProperties,
                                'queryable_properties.admin.E005')

    def test_admin_date_hierarchy_invalid_field(self, monkeypatch):
        monkeypatch.setattr(ApplicationWithClassBasedPropertiesAdmin, 'date_hierarchy', 'neither_property_nor_field')
        assert_admin_validation(ApplicationWithClassBasedPropertiesAdmin, ApplicationWithClassBasedProperties,
                                'admin.E127', "'neither_property_nor_field' that is missing from model")

    @pytest.mark.parametrize('filter_item', [
        DummyListFilter,
        ('common_data', AllValuesFieldListFilter),
        ('support_start_date', AllValuesFieldListFilter),
    ])
    def test_admin_list_filter_valid_items(self, monkeypatch, filter_item):
        monkeypatch.setattr(ApplicationWithClassBasedPropertiesAdmin, 'list_filter', (filter_item,))
        assert_admin_validation(ApplicationWithClassBasedPropertiesAdmin, ApplicationWithClassBasedProperties)

    @pytest.mark.parametrize('filter_item, error_id', [
        ('major_minor', 'queryable_properties.admin.E002'),
        ('is_supported__isnull', 'queryable_properties.admin.E004'),
    ])
    def test_admin_list_filter_invalid_property(self, monkeypatch, filter_item, error_id):
        monkeypatch.setattr(VersionWithClassBasedPropertiesAdmin, 'list_filter', (filter_item,))
        assert_admin_validation(VersionWithClassBasedPropertiesAdmin, VersionWithClassBasedProperties,
                                error_id, '({})'.format(error_id))

    @pytest.mark.parametrize('filter_item, error_id, exception_text', [
        (Dummy, 'admin.E113', "'Dummy' which is not a descendant of ListFilter"),
        (AllValuesFieldListFilter, 'admin.E114', "'AllValuesFieldListFilter' which is of type FieldListFilter"),
        (('version_count', DummyListFilter), 'admin.E115', "'DummyListFilter' which is not of type FieldListFilter"),
        ('neither_property_nor_field', 'admin.E116', "'neither_property_nor_field' which does not refer to a Field"),
    ])
    def test_admin_list_filter_invalid_items(self, monkeypatch, filter_item, error_id, exception_text):
        monkeypatch.setattr(ApplicationWithClassBasedPropertiesAdmin, 'list_filter', (filter_item,))
        assert_admin_validation(ApplicationWithClassBasedPropertiesAdmin, ApplicationWithClassBasedProperties,
                                error_id, exception_text)
