# -*- coding: utf-8 -*-

from queryable_properties.admin import QueryablePropertiesAdmin


class VersionWithClassBasedPropertiesAdmin(QueryablePropertiesAdmin):
    list_display = ('version', 'application', 'is_supported')
    list_filter = ('is_supported', 'released_in_2018')
    search_fields = ('changes', 'version')
    date_hierarchy = 'supported_from'
    list_select_properties = ('version',)
