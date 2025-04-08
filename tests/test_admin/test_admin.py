# -*- coding: utf-8 -*-

import pytest
from django import VERSION as DJANGO_VERSION
from django.contrib.admin import site
from django.contrib.admin.filters import ChoicesFieldListFilter, FieldListFilter
from django.contrib.admin.options import ModelAdmin
from django.db.models.query import QuerySet
from mock import Mock, patch

from queryable_properties.admin import QueryablePropertiesChangeListMixin
from queryable_properties.compat import nullcontext
from queryable_properties.managers import QueryablePropertiesQuerySetMixin
from queryable_properties.utils import get_queryable_property
from ..app_management.admin import ApplicationAdmin, VersionAdmin, VersionInline
from ..app_management.models import ApplicationWithClassBasedProperties, VersionWithClassBasedProperties
from ..marks import skip_if_no_expressions
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
         (get_queryable_property(ApplicationWithClassBasedProperties, 'version_count'),)),
        (ApplicationAdmin, ApplicationWithClassBasedProperties, True,
         (get_queryable_property(ApplicationWithClassBasedProperties, 'version_count'),)),
    ])
    def test_get_queryset(self, rf, admin_class, model, apply_patch, expected_selected_properties):
        admin = admin_class(model, site)
        qs_patch = nullcontext()
        if apply_patch:
            method_name = 'get_queryset' if hasattr(ModelAdmin, 'get_queryset') else 'queryset'
            qs_patch = patch('django.contrib.admin.options.ModelAdmin.{}'.format(method_name),
                             return_value=QuerySet(model))

        with qs_patch:
            queryset = admin.get_queryset(rf.get('/'))
        assert queryset.model is model
        assert isinstance(queryset, QueryablePropertiesQuerySetMixin)
        assert len(queryset.query._queryable_property_annotations) == len(expected_selected_properties)
        for prop in expected_selected_properties:
            assert any(ref.property is prop for ref in queryset.query._queryable_property_annotations)

    @pytest.mark.parametrize('admin_class, model', [
        (ApplicationAdmin, ApplicationWithClassBasedProperties),
        (VersionAdmin, VersionWithClassBasedProperties),
    ])
    def test_get_changelist(self, rf, admin_class, model):
        admin = admin_class(model, site)
        cls = admin.get_changelist(rf.get('/'))
        assert issubclass(cls, QueryablePropertiesChangeListMixin)

    @pytest.mark.skipif(DJANGO_VERSION < (2, 1), reason='Arbitrary search fields were not allowed before Django 2.1')
    @pytest.mark.django_db
    @pytest.mark.parametrize('search_term, expected_count', [
        ('app', 2),
        ('cool', 1),
        ('another', 1),
        ('not-found', 0),
        ('2.0.0', 1),
        ('1.3.1', 1),
        ('1.3', 1),
        ('1.3.0', 0),
        ('1.2.3', 0),
        ('3.4.5', 0),
    ])
    @pytest.mark.usefixtures('versions')
    def test_get_search_results(self, rf, applications, search_term, expected_count):
        applications[0].versions.filter(version='2.0.0').delete()
        request = rf.get('/')
        admin = ApplicationAdmin(ApplicationWithClassBasedProperties, site)
        queryset = admin.get_search_results(request, admin.get_queryset(request), search_term)[0]
        assert queryset.count() == expected_count


@pytest.mark.django_db
class TestQueryablePropertiesChangeListMixin(object):

    @pytest.mark.parametrize('list_display_item, expect_replacement', [
        ('major', False),
        (lambda obj: 'test', False),
        ('is_supported', False),
        pytest.param('application__version_count', True, marks=[skip_if_no_expressions]),
    ])
    def test_initializer_list_display(self, monkeypatch, changelist_factory, list_display_item, expect_replacement):
        has_sortable_by = DJANGO_VERSION >= (2, 1)
        monkeypatch.setattr(VersionAdmin, 'list_display', ('minor', list_display_item))
        monkeypatch.setattr(VersionAdmin, 'list_display_links', ('minor', list_display_item))
        if has_sortable_by:
            monkeypatch.setattr(VersionAdmin, 'sortable_by', ('minor', list_display_item))
        admin = VersionAdmin(VersionWithClassBasedProperties, site)
        changelist = changelist_factory(admin)
        assert changelist.list_display[-2] == changelist.list_display_links[0] == 'minor'
        if has_sortable_by:
            assert changelist.sortable_by[0] == 'minor'
        if expect_replacement:
            replacement = changelist.list_display[-1]
            assert callable(replacement)
            assert replacement(Mock(**{list_display_item: 1337})) == 1337
            assert replacement.short_description == 'Version count'
            assert replacement.admin_order_field == list_display_item
            assert changelist.list_display_links[1] is replacement
            if has_sortable_by:
                assert changelist.sortable_by[1] is replacement
            assert changelist._related_display_properties[list_display_item] is replacement
        else:
            assert changelist.list_display[-1] == changelist.list_display_links[1] == list_display_item
            if has_sortable_by:
                assert changelist.sortable_by[1] == list_display_item

    @pytest.mark.parametrize('list_filter_item, property_name', [
        ('name', None),
        (DummyListFilter, None),
        ('support_start_date', 'support_start_date'),
        (('support_start_date', ChoicesFieldListFilter), 'support_start_date'),
    ])
    def test_initializer_list_filter(self, monkeypatch, rf, changelist_factory, list_filter_item, property_name):
        monkeypatch.setattr(ApplicationAdmin, 'list_filter', ('common_data', list_filter_item))
        admin = ApplicationAdmin(ApplicationWithClassBasedProperties, site)
        changelist = changelist_factory(admin)
        assert changelist.list_filter[0] == 'common_data'
        assert (changelist.list_filter[1] == list_filter_item) is (not property_name)
        if property_name:
            replacement = changelist.list_filter[1]
            assert callable(replacement)
            filter_instance = replacement(rf.get('/'), {}, admin.model, admin)
            assert isinstance(filter_instance, FieldListFilter)
            assert filter_instance.field.name == property_name

    @skip_if_no_expressions
    def test_get_queryset(self, monkeypatch, rf, changelist_factory, versions):
        versions[0].delete()
        monkeypatch.setattr(VersionAdmin, 'list_display',
                            ('major', 'application__version_count', 'application__major_sum'))
        admin = VersionAdmin(VersionWithClassBasedProperties, site)
        changelist = changelist_factory(admin)
        for version in changelist.get_queryset(rf.get('/')):
            app_has_all_versions = version in versions[4:]
            assert version.application__version_count == (3 + app_has_all_versions)
            assert version.application__major_sum == (4 + app_has_all_versions)
