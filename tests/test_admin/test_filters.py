# -*- coding: utf-8 -*-

import pytest
from django import VERSION as DJANGO_VERSION
from django.contrib.admin import ModelAdmin, site
from django.contrib.admin.filters import BooleanFieldListFilter, ChoicesFieldListFilter, DateFieldListFilter
from django.contrib.admin.views.main import ChangeList
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

    def get_changelist(self, request, model_admin, **kwargs):
        """
        Build a changelist instance for the given admin for testing purposes.

        :param django.http.HttpRequest request: An HTTP request.
        :param model_admin: The model admin to create the changelist for.
        :param kwargs: Further keyword arguments for the changelist
                       constructor, which will otherwise be filled with
                       proper default values.
        :return: The changelist instance.
        :rtype: ChangeList
        """
        list_display = kwargs.get('list_display', model_admin.get_list_display(request))
        defaults = dict(
            model=model_admin.model,
            list_display=list_display,
            list_display_links=model_admin.get_list_display_links(request, list_display),
            list_filter=model_admin.get_list_filter(request) if DJANGO_VERSION >= (1, 5) else model_admin.list_filter,
            date_hierarchy=model_admin.date_hierarchy,
            search_fields=model_admin.search_fields,
            list_select_related=model_admin.list_select_related,
            list_per_page=model_admin.list_per_page,
            list_max_show_all=model_admin.list_max_show_all,
            list_editable=model_admin.list_editable,
            model_admin=model_admin
        )
        if hasattr(ModelAdmin, 'get_sortable_by'):
            defaults['sortable_by'] = model_admin.get_sortable_by(request)
        defaults.update(kwargs)
        return ChangeList(request, **defaults)

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

    @pytest.mark.django_db
    def test_date_list_filter(self, rf, admin_user, admin_instance):
        field = QueryablePropertyField(admin_instance, 'support_start_date')
        field.output_field = DateField(null=True)  # To set an output field for Django versions that don't support it
        request = rf.get('/')
        request.user = admin_user
        list_filter = field.get_filter_creator()(request, {}, admin_instance.model, admin_instance)
        changelist = self.get_changelist(request, admin_instance)
        display_values = [item['display'] for item in list_filter.choices(changelist)]
        expected_values = ['Any date', 'Today', 'Past 7 days', 'This month', 'This year']
        if DJANGO_VERSION >= (1, 10):
            expected_values += ['No date', 'Has date']
        assert display_values == expected_values

    @pytest.mark.django_db
    @pytest.mark.parametrize('params, expected_count', [
        ({}, 2),
        ({'support_start_date__gte': '2016-12-15', 'support_start_date__lt': '2017-01-15'}, 2),
        ({'support_start_date__gte': '2016-12-31', 'support_start_date__lt': '2017-01-31'}, 2),
        ({'support_start_date__gte': '2016-11-15', 'support_start_date__lt': '2016-12-31'}, 0),
        ({'support_start_date__gte': '2018-01-01', 'support_start_date__lt': '2018-12-31'}, 0),
    ])
    @pytest.mark.usefixtures('versions')
    def test_date_list_filter_application(self, rf, admin_user, admin_instance, params, expected_count):
        field = QueryablePropertyField(admin_instance, 'support_start_date')
        field.output_field = DateField(null=True)  # To set an output field for Django versions that don't support it
        request = rf.get('/')
        request.user = admin_user
        list_filter = field.get_filter_creator()(request, params, admin_instance.model, admin_instance)
        assert list_filter.queryset(request, admin_instance.get_queryset(request)).count() == expected_count

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    @pytest.mark.django_db
    def test_boolean_list_filter(self, rf, admin_user, admin_instance):
        field = QueryablePropertyField(admin_instance, 'has_version_with_changelog')
        assert tuple(field.flatchoices) == ()

        request = rf.get('/')
        request.user = admin_user
        list_filter = field.get_filter_creator()(request, {}, admin_instance.model, admin_instance)
        changelist = self.get_changelist(request, admin_instance)
        display_values = [item['display'] for item in list_filter.choices(changelist)]
        assert display_values == ['All', 'Yes', 'No']

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    @pytest.mark.django_db
    @pytest.mark.parametrize('params, expected_count', [
        ({}, 2),
        ({'has_version_with_changelog__exact': '0'}, 1),
        ({'has_version_with_changelog__exact': '1'}, 1),
    ])
    def test_boolean_list_filter_application(self, rf, admin_user, versions, admin_instance, params, expected_count):
        versions[3].delete()
        field = QueryablePropertyField(admin_instance, 'has_version_with_changelog')
        request = rf.get('/')
        request.user = admin_user
        list_filter = field.get_filter_creator()(request, params, admin_instance.model, admin_instance)
        assert list_filter.queryset(request, admin_instance.get_queryset(request)).count() == expected_count

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    @pytest.mark.django_db
    def test_mapping_choices_list_filter(self, rf, admin_user):
        admin = VersionAdmin(VersionWithClassBasedProperties, site)
        field = QueryablePropertyField(admin, 'release_type_verbose_name')
        assert tuple(field.flatchoices) == (
            ('Alpha', 'Alpha'),
            ('Beta', 'Beta'),
            ('Stable', 'Stable'),
            (None, field.empty_value_display),
        )

        request = rf.get('/')
        request.user = admin_user
        list_filter = field.get_filter_creator()(request, {}, admin.model, admin)
        changelist = self.get_changelist(request, admin)
        display_values = [item['display'] for item in list_filter.choices(changelist)]
        assert display_values == ['All', 'Alpha', 'Beta', 'Stable', field.empty_value_display]

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    @pytest.mark.django_db
    @pytest.mark.parametrize('params, expected_count', [
        ({}, 8),
        ({'release_type_verbose_name__exact': 'Alpha'}, 2),
        ({'release_type_verbose_name__exact': 'Beta'}, 2),
        ({'release_type_verbose_name__exact': 'Stable'}, 4),
    ])
    @pytest.mark.usefixtures('versions')
    def test_mapping_choices_list_filter_application(self, rf, admin_user, params, expected_count):
        admin = VersionAdmin(VersionWithClassBasedProperties, site)
        field = QueryablePropertyField(admin, 'release_type_verbose_name')
        request = rf.get('/')
        request.user = admin_user
        list_filter = field.get_filter_creator()(request, params, admin.model, admin)
        assert list_filter.queryset(request, admin.get_queryset(request)).count() == expected_count

    @pytest.mark.django_db
    @pytest.mark.parametrize('query_path, expected_choices', [
        ('version_count', ((3, '3'), (4, '4'))),
        ('categories__version_count', ((4, '4'), (7, '7'))),
    ])
    def test_choices_list_filter(self, rf, admin_user, versions, admin_instance, query_path, expected_choices):
        versions[0].delete()
        field = QueryablePropertyField(admin_instance, query_path)
        assert tuple(field.flatchoices) == expected_choices

        request = rf.get('/')
        request.user = admin_user
        list_filter = field.get_filter_creator()(request, {}, admin_instance.model, admin_instance)
        changelist = self.get_changelist(request, admin_instance)
        display_values = [item['display'] for item in list_filter.choices(changelist)]
        assert display_values == ['All'] + [display_value for value, display_value in expected_choices]

    @pytest.mark.django_db
    @pytest.mark.parametrize('params, expected_count', [
        ({}, 2),
        ({'version_count__exact': '3'}, 1),
        ({'version_count__exact': '4'}, 1),
        ({'version_count__exact': '5'}, 0),
    ])
    def test_choices_list_filter_application(self, rf, admin_user, versions, admin_instance, params, expected_count):
        versions[0].delete()
        field = QueryablePropertyField(admin_instance, 'version_count')
        request = rf.get('/')
        request.user = admin_user
        list_filter = field.get_filter_creator()(request, params, admin_instance.model, admin_instance)
        assert list_filter.queryset(request, admin_instance.get_queryset(request)).count() == expected_count


class TestQueryablePropertyListFilter(object):

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Output fields couldn't be declared before Django 1.8")
    @pytest.mark.parametrize('prop, admin_class, expected_filter_class', [
        (ApplicationWithClassBasedProperties.has_version_with_changelog, ApplicationAdmin, BooleanFieldListFilter),
        (VersionWithClassBasedProperties.release_type_verbose_name, VersionAdmin, ChoicesFieldListFilter),
        (ApplicationWithClassBasedProperties.support_start_date, VersionAdmin, DateFieldListFilter),
        (VersionWithClassBasedProperties.version, VersionAdmin, ChoicesFieldListFilter),
    ])
    def test_get_class(self, prop, admin_class, expected_filter_class):
        field = QueryablePropertyField(admin_class(prop.model, site), prop.name)
        assert QueryablePropertyListFilter.get_class(field) is expected_filter_class
