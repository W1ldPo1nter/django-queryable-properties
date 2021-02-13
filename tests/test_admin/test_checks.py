# -*- coding: utf-8 -*-

import pytest
import six
from django import VERSION as DJANGO_VERSION
from django.contrib.admin import ModelAdmin, site
from django.core.exceptions import ImproperlyConfigured

from queryable_properties.compat import admin_validation
from ..app_management.admin import VersionWithClassBasedPropertiesAdmin
from ..app_management.models import VersionWithClassBasedProperties


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
            assert exception_text in six.text_type(e)
        else:
            assert exception_text is None


class TestQueryablePropertiesChecksMixin(object):

    @pytest.mark.parametrize('admin, model', [
        (VersionWithClassBasedPropertiesAdmin, VersionWithClassBasedProperties),
    ])
    def test_admin_success(self, admin, model):
        assert_admin_validation(admin, model)
