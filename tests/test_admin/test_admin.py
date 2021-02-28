# -*- coding: utf-8 -*-

import pytest
from django.contrib.admin import site
from django.contrib.admin.filters import ChoicesFieldListFilter, FieldListFilter
from django.db.models.query import QuerySet
from mock import patch

from queryable_properties.compat import nullcontext
from queryable_properties.managers import QueryablePropertiesQuerySetMixin
from ..app_management.admin import ApplicationAdmin, VersionAdmin, VersionInline
from ..app_management.models import ApplicationWithClassBasedProperties, VersionWithClassBasedProperties
from .test_checks import DummyListFilter


class TestQueryablePropertiesAdminMixin(object):

    @pytest.mark.parametrize('admin_class, model, expected_value', [
        (VersionAdmin, VersionWithClassBasedProperties, ()),
        (ApplicationAdmin, ApplicationWithClassBasedProperties, ('version_count',)),
        (VersionInline, ApplicationWithClassBasedProperties, ('changes_or_default',)),
    ])
    def test_get_list_select_properties(self, rf, admin_class, model, expected_value):
        admin = admin_class(model, site)
        assert admin.get_list_select_properties(rf.get('/')) == expected_value

    @pytest.mark.parametrize('admin_class, model, apply_patch, expected_selected_properties', [
        (VersionAdmin, VersionWithClassBasedProperties, False, ()),
        (VersionAdmin, VersionWithClassBasedProperties, True, ()),
        (ApplicationAdmin, ApplicationWithClassBasedProperties, False,
         (ApplicationWithClassBasedProperties.version_count,)),
        (ApplicationAdmin, ApplicationWithClassBasedProperties, True,
         (ApplicationWithClassBasedProperties.version_count,)),
    ])
    def test_get_queryset(self, rf, admin_class, model, apply_patch, expected_selected_properties):
        admin = admin_class(model, site)
        qs_patch = nullcontext()
        if apply_patch:
            qs_patch = patch('django.contrib.admin.options.ModelAdmin.get_queryset', return_value=QuerySet(model))

        with qs_patch:
            queryset = admin.get_queryset(rf.get('/'))
        assert queryset.model is model
        assert isinstance(queryset, QueryablePropertiesQuerySetMixin)
        assert len(queryset.query._queryable_property_annotations) == len(expected_selected_properties)
        for prop in expected_selected_properties:
            assert any(ref.property is prop for ref in queryset.query._queryable_property_annotations)

    @pytest.mark.parametrize('list_filter_item, property_name', [
        ('name', None),
        (DummyListFilter, None),
        ('support_start_date', 'support_start_date'),
        (('support_start_date', ChoicesFieldListFilter), 'support_start_date'),
    ])
    def test_get_list_filter(self, monkeypatch, rf, list_filter_item, property_name):
        monkeypatch.setattr(ApplicationAdmin, 'list_filter', ('common_data', list_filter_item))
        admin = ApplicationAdmin(ApplicationWithClassBasedProperties, site)
        list_filter = admin.get_list_filter(rf.get('/'))
        assert list_filter[0] == 'common_data'
        assert (list_filter[1] == list_filter_item) is (not property_name)
        if property_name:
            replacement = list_filter[1]
            assert callable(replacement)
            filter_instance = replacement(rf.get('/'), {}, admin.model, admin)
            assert isinstance(filter_instance, FieldListFilter)
            assert filter_instance.field.name == property_name
