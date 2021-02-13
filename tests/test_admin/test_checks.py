# -*- coding: utf-8 -*-

import pytest
import six
from django import VERSION as DJANGO_VERSION
from django.contrib.admin import ModelAdmin, site
from django.core.exceptions import ImproperlyConfigured

from queryable_properties.compat import admin_validation
from ..app_management.admin import ApplicationWithClassBasedPropertiesAdmin, VersionWithClassBasedPropertiesAdmin
from ..app_management.models import ApplicationWithClassBasedProperties, VersionWithClassBasedProperties


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

    def test_admin_non_annotatable_date_hierarchy_property(self, monkeypatch):
        monkeypatch.setattr(VersionWithClassBasedPropertiesAdmin, 'date_hierarchy', 'major_minor')
        assert_admin_validation(VersionWithClassBasedPropertiesAdmin, VersionWithClassBasedProperties,
                                'queryable_properties.admin.E001', '(queryable_properties.admin.E001)')

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="output fields couldn't be declared before Django 1.8")
    def test_admin_date_hierarchy_invalid_type(self, monkeypatch):
        monkeypatch.setattr(ApplicationWithClassBasedPropertiesAdmin, 'date_hierarchy', 'highest_version')
        assert_admin_validation(ApplicationWithClassBasedPropertiesAdmin, ApplicationWithClassBasedProperties,
                                'queryable_properties.admin.E003')

    def test_admin_date_hierarchy_invalid_field(self, monkeypatch):
        monkeypatch.setattr(ApplicationWithClassBasedPropertiesAdmin, 'date_hierarchy', 'neither_property_nor_field')
        assert_admin_validation(ApplicationWithClassBasedPropertiesAdmin, ApplicationWithClassBasedProperties,
                                'admin.E127', "'neither_property_nor_field' that is missing from model")
