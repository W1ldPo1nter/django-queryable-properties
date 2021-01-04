# -*- coding: utf-8 -*-

from copy import deepcopy

from django.contrib.admin import ModelAdmin, StackedInline, TabularInline
from django.db.models import F

try:
    from django.db.models.expressions import Combinable, OrderBy
except ImportError:
    Combinable = OrderBy = None

from .compat import chain_queryset, LOOKUP_SEP
from .managers import QueryablePropertiesQuerySetMixin
from .utils.internal import resolve_queryable_property


class QueryablePropertiesAdminMixin(object):

    list_select_properties = None

    def __init__(self, *args, **kwargs):
        super(QueryablePropertiesAdminMixin, self).__init__(*args, **kwargs)
        self._ordering_with_properties = None
        if self.ordering is not None:
            # Filter out all queryable property references as they wouldn't
            # pass Django's checks. Maintain the real ordering in a different
            # attribute instead.
            self._ordering_with_properties = deepcopy(self.ordering)
            self.ordering = [ordering_item for ordering_item in self.ordering
                             if not self._is_queryable_property_ordering(ordering_item)]

    def _is_queryable_property_ordering(self, ordering_item):
        if Combinable is not None:
            if isinstance(ordering_item, Combinable):
                ordering_item = ordering_item.asc()
            if isinstance(ordering_item, OrderBy) and isinstance(ordering_item.expression, F):
                ordering_item = ordering_item.expression.name
            else:
                return False
        if ordering_item.startswith('-') or ordering_item.startswith('+'):
            ordering_item = ordering_item[1:]
        return bool(resolve_queryable_property(self.model, ordering_item.split(LOOKUP_SEP))[0])

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

    def get_ordering(self, request):
        return self._ordering_with_properties or super(QueryablePropertiesAdminMixin, self).get_ordering(request)

    def get_list_select_properties(self):
        return self.list_select_properties


class QueryablePropertiesAdmin(QueryablePropertiesAdminMixin, ModelAdmin):

    pass


class QueryablePropertiesStackedInline(QueryablePropertiesAdminMixin, StackedInline):

    pass


class QueryablePropertiesTabularInline(QueryablePropertiesAdminMixin, TabularInline):

    pass
