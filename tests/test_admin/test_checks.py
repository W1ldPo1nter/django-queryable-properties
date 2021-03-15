# -*- coding: utf-8 -*-

import pytest
import six
from django import VERSION as DJANGO_VERSION
from django.contrib.admin import ModelAdmin, SimpleListFilter, site
from django.contrib.admin.filters import AllValuesFieldListFilter
from django.core.exceptions import ImproperlyConfigured
from django.db.models import F

from queryable_properties.admin.checks import Error
from queryable_properties.compat import admin_validation
from ..app_management.admin import ApplicationAdmin, VersionAdmin, VersionInline
from ..app_management.models import ApplicationWithClassBasedProperties, VersionWithClassBasedProperties
from ..conftest import Concat, Value


class Dummy(object):

    def __str__(self):
        return self.__class__.__name__


class DummyListFilter(SimpleListFilter):
    parameter_name = 'dummy'


def assert_admin_validation(admin_class, model, error_id=None, exception_text=None):
    """
    Validate an admin class and compare the result to the given expectation.

    :param admin_class: The admin class to validate (may be an inline class).
    :param model: The model class the admin class is intended for.
    :param str | None error_id: The expected error ID, which is used for new
                                Django versions. A value of None means that
                                the validation is expected to not find any
                                errors.
    :param str | None exception_text: The expected error text, which is used
                                for old Django versions. A value of None means
                                that the validation is expected to not find any
                                errors.
    """
    if hasattr(ModelAdmin, 'check'):
        if DJANGO_VERSION >= (1, 9):
            errors = admin_class(model, site).check()
        else:
            errors = admin_class.check(model)
        if error_id is None:
            assert not errors
        else:
            assert any(error.id == error_id for error in errors)

    if hasattr(admin_validation, 'validate') or hasattr(ModelAdmin, 'validate'):
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


class TestError(object):

    def test_initializer(self):
        error = Error('test message', Dummy, 42)
        assert error.msg == 'test message'
        assert error.obj is Dummy
        assert error.id == 'queryable_properties.admin.E042'

    def test_raise_exception(self):
        error = Error('test message', Dummy(), 42)
        with pytest.raises(ImproperlyConfigured, match=r'Dummy: \(queryable_properties\.admin\.E042\) test message'):
            error.raise_exception()


class TestQueryablePropertiesChecksMixin(object):

    @pytest.mark.parametrize('admin, model', [
        (VersionAdmin, VersionWithClassBasedProperties),
        (ApplicationAdmin, ApplicationWithClassBasedProperties),
    ])
    def test_success(self, admin, model):
        assert_admin_validation(admin, model)

    @pytest.mark.parametrize('filter_item', [
        DummyListFilter,
        ('common_data', AllValuesFieldListFilter),
        ('support_start_date', AllValuesFieldListFilter),
    ])
    def test_list_filter_valid_items(self, monkeypatch, filter_item):
        monkeypatch.setattr(ApplicationAdmin, 'list_filter', (filter_item,))
        assert_admin_validation(ApplicationAdmin, ApplicationWithClassBasedProperties)

    @pytest.mark.parametrize('filter_item, error_id', [
        ('major_minor', 'queryable_properties.admin.E002'),
        ('is_supported__isnull', 'queryable_properties.admin.E004'),
    ])
    def test_list_filter_invalid_property(self, monkeypatch, filter_item, error_id):
        monkeypatch.setattr(VersionAdmin, 'list_filter', (filter_item,))
        assert_admin_validation(VersionAdmin, VersionWithClassBasedProperties, error_id, '({})'.format(error_id))

    @pytest.mark.parametrize('filter_item, error_id, exception_text', [
        (Dummy, 'admin.E113', "'Dummy' which is not a descendant of ListFilter"),
        (AllValuesFieldListFilter, 'admin.E114', "'AllValuesFieldListFilter' which is of type FieldListFilter"),
        (('version_count', DummyListFilter), 'admin.E115', "'DummyListFilter' which is not of type FieldListFilter"),
        ('neither_property_nor_field', 'admin.E116', "'neither_property_nor_field' which does not refer to a Field"),
    ])
    def test_list_filter_invalid_items(self, monkeypatch, filter_item, error_id, exception_text):
        monkeypatch.setattr(ApplicationAdmin, 'list_filter', (filter_item,))
        assert_admin_validation(ApplicationAdmin, ApplicationWithClassBasedProperties, error_id, exception_text)

    @pytest.mark.parametrize('admin_class', [ApplicationAdmin, VersionInline])
    def test_list_select_properties_invalid_type(self, monkeypatch, admin_class):
        monkeypatch.setattr(admin_class, 'list_select_properties', None)
        assert_admin_validation(ApplicationAdmin, ApplicationWithClassBasedProperties,
                                'queryable_properties.admin.E005', '(queryable_properties.admin.E005)')

    @pytest.mark.parametrize('admin_class, property_name, error_id', [
        (ApplicationAdmin, 'name', 'queryable_properties.admin.E001'),
        (VersionInline, 'major', 'queryable_properties.admin.E001'),
        (ApplicationAdmin, 'dummy', 'queryable_properties.admin.E002'),
        (VersionInline, 'major_minor', 'queryable_properties.admin.E002'),
        (ApplicationAdmin, 'categories__version_count', 'queryable_properties.admin.E003'),
        (VersionInline, 'application__categories__version_count', 'queryable_properties.admin.E003'),
        (ApplicationAdmin, 'version_count__lt', 'queryable_properties.admin.E004'),
        (VersionInline, 'version__regex', 'queryable_properties.admin.E004'),
    ])
    def test_list_select_properties_invalid_property(self, monkeypatch, admin_class, property_name, error_id):
        monkeypatch.setattr(admin_class, 'list_select_properties', (property_name,))
        assert_admin_validation(ApplicationAdmin, ApplicationWithClassBasedProperties,
                                error_id, '({})'.format(error_id))

    @pytest.mark.parametrize('admin_class, property_name', [
        (ApplicationAdmin, 'version_count'),
        (VersionInline, 'version'),
    ])
    def test_ordering_valid_desc(self, monkeypatch, admin_class, property_name):
        monkeypatch.setattr(admin_class, 'ordering', ('-' + property_name,))
        assert_admin_validation(ApplicationAdmin, ApplicationWithClassBasedProperties)

    @pytest.mark.skipif(DJANGO_VERSION < (2, 0), reason="Expression-based ordering wasn't supported before Django 2.0")
    @pytest.mark.parametrize('admin_class, expression', [
        (ApplicationAdmin, F('highest_version')),
        (VersionInline, F('version')),
        (ApplicationAdmin, Concat(Value('V'), 'highest_version')),
        (VersionInline, Concat(Value('V'), 'version')),
        (ApplicationAdmin, Concat(Value('V'), 'highest_version').desc()),
        (VersionInline, Concat(Value('V'), 'version').desc()),
    ])
    def test_ordering_valid_expressions(self, monkeypatch, admin_class, expression):
        monkeypatch.setattr(admin_class, 'ordering', (expression,))
        assert_admin_validation(ApplicationAdmin, ApplicationWithClassBasedProperties)

    @pytest.mark.parametrize('admin_class, property_name', [
        (ApplicationAdmin, 'dummy'),
        (VersionInline, 'major_minor'),
    ])
    def test_ordering_invalid_property(self, monkeypatch, admin_class, property_name):
        monkeypatch.setattr(admin_class, 'ordering', (property_name,))
        assert_admin_validation(ApplicationAdmin, ApplicationWithClassBasedProperties,
                                'queryable_properties.admin.E002', '(queryable_properties.admin.E002)')
