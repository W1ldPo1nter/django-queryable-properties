# -*- coding: utf-8 -*-

from collections import OrderedDict

import six
from django.contrib.admin.filters import (BooleanFieldListFilter, ChoicesFieldListFilter, DateFieldListFilter,
                                          FieldListFilter)
from django.db.models import BooleanField, DateField, F

from ..compat import LOOKUP_SEP
from ..exceptions import QueryablePropertyError
from ..properties import MappingProperty
from ..utils.internal import get_output_field, resolve_queryable_property


class QueryablePropertyField(object):

    def __init__(self, model_admin, request, query_path):
        property_ref, lookups = resolve_queryable_property(model_admin.model, query_path.split(LOOKUP_SEP))
        if not property_ref or lookups:
            raise QueryablePropertyError('The query path must point to a valid queryable property and may not contain'
                                         'lookups/transforms.')

        self.output_field = get_output_field(property_ref.get_annotation())
        self.model_admin = model_admin
        self.request = request
        self.property = property_ref.property
        self.property_path = query_path
        self.null = self.output_field is None or self.output_field.null
        self.empty_strings_allowed = self.output_field is None or self.output_field.empty_strings_allowed

    def __getattr__(self, item):
        return getattr(self.property, item)

    @property
    def flatchoices(self):
        if isinstance(self.property, MappingProperty):
            options = OrderedDict((to_value, to_value) for from_value, to_value in self.property.mappings)
            options.setdefault(self.property.default, self.model_admin.get_empty_value_display())
            for value, label in six.iteritems(options):
                yield value, label
        elif not isinstance(self.output_field, BooleanField):
            annotation_name = '{}value'.format(LOOKUP_SEP)
            queryset = self.model_admin.get_queryset(self.request).annotate(**{annotation_name: F(self.property_path)})
            queryset = queryset.order_by(annotation_name).distinct().values_list(annotation_name, flat=True)
            for value in queryset:
                yield value, value

    def create_list_filter(self, list_filter_class=None):
        list_filter_class = list_filter_class or QueryablePropertyListFilter.get_class(self)

        def creator(request, params, model, model_admin):
            return list_filter_class(self, request, params, model, model_admin, self.property_path)
        return creator


class QueryablePropertyListFilter(FieldListFilter):
    _field_list_filters = []
    _take_priority_index = 0

    @classmethod
    def get_class(cls, field):
        for test, list_filter_class in cls._field_list_filters:
            if test(field):
                return list_filter_class


QueryablePropertyListFilter.register(lambda field: isinstance(field.output_field, BooleanField), BooleanFieldListFilter)
QueryablePropertyListFilter.register(lambda field: isinstance(field.property, MappingProperty), ChoicesFieldListFilter)
QueryablePropertyListFilter.register(lambda field: isinstance(field.output_field, DateField), DateFieldListFilter)
QueryablePropertyListFilter.register(lambda field: True, ChoicesFieldListFilter)
