# -*- coding: utf-8 -*-

import six
from django.contrib.admin import ModelAdmin, StackedInline, TabularInline
from django.contrib.admin.options import BaseModelAdmin

from ..compat import chain_queryset
from ..exceptions import QueryablePropertyError
from ..managers import QueryablePropertiesQuerySetMixin
from .checks import QueryablePropertiesChecksMixin
from .filters import QueryablePropertyField


class QueryablePropertiesAdminMeta(type(BaseModelAdmin)):

    CHECK_ATTRIBUTES = ('checks_class', 'default_validator_class', 'validator_class')

    def __new__(mcs, name, bases, attrs):
        # Mix a check mixin into any checks/validator class if that hasn't
        # happened already.
        for attr in mcs.CHECK_ATTRIBUTES:
            check_class = attrs.get(attr)
            for base in bases:
                if check_class is None:
                    check_class = getattr(base, attr, None)
            if check_class and not issubclass(check_class, QueryablePropertiesChecksMixin):
                class_name = 'QueryableProperties' + check_class.__name__
                attrs[attr] = QueryablePropertiesChecksMixin.mix_with_class(check_class, class_name)
        return super(QueryablePropertiesAdminMeta, mcs).__new__(mcs, name, bases, attrs)


class QueryablePropertiesAdminMixin(six.with_metaclass(QueryablePropertiesAdminMeta, object)):

    list_select_properties = None

    def get_queryset(self, request):
        queryset = super(QueryablePropertiesAdminMixin, self).get_queryset(request)
        # Make sure to use a queryset with queryable properties features.
        if not isinstance(queryset, QueryablePropertiesQuerySetMixin):
            queryset = chain_queryset(queryset)
            QueryablePropertiesQuerySetMixin.inject_into_object(queryset)
        # Apply list_select_properties.
        list_select_properties = self.get_list_select_properties()
        if list_select_properties:
            queryset = queryset.select_properties(*list_select_properties)
        return queryset

    def get_list_filter(self, request):
        list_filter = super(QueryablePropertiesAdminMixin, self).get_list_filter(request)
        expanded_filters = []
        for item in list_filter:
            if not callable(item):
                if isinstance(item, (tuple, list)):
                    field_name, filter_class = item
                else:
                    field_name, filter_class = item, None
                try:
                    item = QueryablePropertyField(self, request, field_name).create_list_filter(filter_class)
                except QueryablePropertyError:
                    pass
            expanded_filters.append(item)
        return expanded_filters

    def get_list_select_properties(self):
        return self.list_select_properties


class QueryablePropertiesAdmin(QueryablePropertiesAdminMixin, ModelAdmin):

    pass


class QueryablePropertiesStackedInline(QueryablePropertiesAdminMixin, StackedInline):

    pass


class QueryablePropertiesTabularInline(QueryablePropertiesAdminMixin, TabularInline):

    pass
