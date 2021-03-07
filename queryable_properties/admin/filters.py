# -*- coding: utf-8 -*-

from collections import OrderedDict

import six
from django.contrib.admin.filters import (BooleanFieldListFilter, ChoicesFieldListFilter, DateFieldListFilter,
                                          FieldListFilter)
from django.contrib.admin.views import main
from django.db.models import BooleanField, DateField

from ..compat import LOOKUP_SEP
from ..exceptions import QueryablePropertyError
from ..properties import MappingProperty
from ..utils.internal import get_output_field, resolve_queryable_property


class QueryablePropertyField(object):
    """
    Wrapper class for queryable property that offers an attribute interface
    similar to Django fields. This allows to reuse Django's existing list
    filter implementations for queryable properties by providing objects of
    this class to list filters.
    """

    def __init__(self, model_admin, query_path):
        """
        Initialize a new property-to-field interface wrapper for the queryable
        property with the given path.

        :param model_admin: The admin instance for which a filter based on the
                            given queryable property should be created.
        :type model_admin: django.contrib.admin.options.BaseModelAdmin
        :param str query_path: The query path to the queryable property.
        """
        property_ref, lookups = resolve_queryable_property(model_admin.model, query_path.split(LOOKUP_SEP))
        if not property_ref or lookups:
            raise QueryablePropertyError('The query path must point to a valid queryable property and may not contain'
                                         'lookups/transforms.')

        self.output_field = get_output_field(property_ref.get_annotation())
        self.model_admin = model_admin
        self.property = property_ref.property
        self.property_ref = property_ref
        self.property_path = query_path
        self.null = self.output_field is None or self.output_field.null
        self.empty_strings_allowed = self.output_field is None or self.output_field.empty_strings_allowed

    def __getattr__(self, item):
        # Pass through attribute accesses to the associated queryable property.
        # This allows to access properties common to both queryable properties
        # and model fields (e.g. name, verbose_name) without having to copy
        # their values explicitly.
        return getattr(self.property, item)

    @property
    def empty_value_display(self):
        """
        Get the value to display in the admin in place of empty values.

        :return: The value to display for empty internal values.
        :rtype: str
        """
        return getattr(main, 'EMPTY_CHANGELIST_VALUE', None) or self.model_admin.get_empty_value_display()

    @property
    def flatchoices(self):
        """
        Build the list filter choices for the associated queryable property
        as 2-tuples.

        This is an attribute expected by certain list filter classes and is
        used for any queryable property that doesn't map to a specialized
        filter class, which is why the :class:`ChoicesFieldListFilter` is used
        as the last resort when determining filter classes.

        :return: The filter choices as 2-tuples containing the internal value
                 as the first and the display value as the second item.
        :rtype: (object, object)
        """
        if isinstance(self.property, MappingProperty):
            options = OrderedDict((to_value, to_value) for from_value, to_value in self.property.mappings)
            options.setdefault(self.property.default, self.empty_value_display)
            for value, label in six.iteritems(options):
                yield value, label
        elif not isinstance(self.output_field, BooleanField):
            name = '{}value'.format(self.property.name)
            queryset = self.property_ref.model._default_manager.annotate(**{name: self.property_ref.get_annotation()})
            for value in queryset.order_by(name).distinct().values_list(name, flat=True):
                yield value, six.text_type(value) if value is not None else self.empty_value_display

    def get_filter_creator(self, list_filter_class=None):
        """
        Create a callable that can be used to create a list filter object based
        on this property.

        :param list_filter_class: The list filter class to use. If not given,
                                  a suitable list filter class will be
                                  determined for the associated queryable
                                  property.
        :return: A callable to create a list filter object.
        :rtype: collections.Callable
        """
        list_filter_class = list_filter_class or QueryablePropertyListFilter.get_class(self)

        def creator(request, params, model, model_admin):
            return list_filter_class(self, request, params, model, model_admin, self.property_path)
        return creator


class QueryablePropertyListFilter(FieldListFilter):
    """
    A base list filter class for queryable properties that allows to re-use
    Django's filter class registration for queryable properties.
    """
    _field_list_filters = []
    _take_priority_index = 0

    @classmethod
    def get_class(cls, field):
        """
        Determine a suitable list filter class for the given wrapped queryable
        property based on the registered filter classes.

        :param QueryablePropertyField field: The wrapped queryable property.
        :return: An appropriate list filter class.
        """
        for test, list_filter_class in cls._field_list_filters:
            if test(field):
                return list_filter_class


QueryablePropertyListFilter.register(lambda field: isinstance(field.output_field, BooleanField), BooleanFieldListFilter)
QueryablePropertyListFilter.register(lambda field: isinstance(field.property, MappingProperty), ChoicesFieldListFilter)
QueryablePropertyListFilter.register(lambda field: isinstance(field.output_field, DateField), DateFieldListFilter)
# Use the ChoicesFieldListFilter as the last resort since the general
# implementation of "list all possible values" is implemented in
# `QueryablePropertyField.flatchoices`.
# Django's last resort AllValuesFieldListFilter cannot be used as it performs
# a hardcoded query on its own, which wouldn't work with a queryable property.
QueryablePropertyListFilter.register(lambda field: True, ChoicesFieldListFilter)
