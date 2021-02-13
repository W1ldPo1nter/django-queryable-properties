# -*- coding: utf-8 -*-

from queryable_properties.admin import QueryablePropertiesAdmin


class ApplicationWithClassBasedPropertiesAdmin(QueryablePropertiesAdmin):
    list_display = ('name', 'highest_version', 'version_count')
    list_filter = ('common_data', 'support_start_date', 'has_version_with_changelog')
    search_fields = ('name', 'highest_version')
    date_hierarchy = 'support_start_date'
    list_select_properties = ('highest_version', 'version_count')
    ordering = ('highest_version', 'name')


class VersionWithClassBasedPropertiesAdmin(QueryablePropertiesAdmin):
    list_display = ('version', 'application', 'is_supported')
    list_filter = ('is_supported', 'released_in_2018', 'major')
    search_fields = ('changes',)
    date_hierarchy = 'supported_from'
    ordering = ('application', 'major', 'minor', 'patch')
