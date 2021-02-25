# -*- coding: utf-8 -*-

from queryable_properties.admin import QueryablePropertiesAdmin, QueryablePropertiesTabularInline
from ..app_management.models import VersionWithClassBasedProperties


class VersionAdmin(QueryablePropertiesAdmin):
    list_display = ('version', 'application', 'is_supported')
    list_filter = ('is_supported', 'released_in_2018', 'major')
    search_fields = ('changes',)
    date_hierarchy = 'supported_from'
    ordering = ('application', 'major', 'minor', 'patch')


class VersionInline(QueryablePropertiesTabularInline):
    model = VersionWithClassBasedProperties
    list_select_properties = ('changes_or_default',)
    ordering = ('version',)


class ApplicationAdmin(QueryablePropertiesAdmin):
    list_display = ('name', 'highest_version', 'version_count')
    list_filter = ('common_data', 'support_start_date', 'has_version_with_changelog')
    list_select_properties = ('version_count',)
    search_fields = ('name', 'highest_version')
    date_hierarchy = 'support_start_date'
    ordering = ('name', 'version_count')
    inlines = (VersionInline,)
