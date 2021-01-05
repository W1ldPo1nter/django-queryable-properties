# -*- coding: utf-8 -*-

import six
from django.contrib.admin import ModelAdmin, StackedInline, TabularInline
from django.contrib.admin.options import BaseModelAdmin
from django.db.models import F

try:
    from django.db.models.expressions import Combinable, OrderBy
except ImportError:
    Combinable = OrderBy = None

from .compat import chain_queryset, LOOKUP_SEP
from .managers import QueryablePropertiesQuerySetMixin
from .utils.internal import InjectableMixin, resolve_queryable_property


# TODO: alternative for Django < 1.9 validators
class QueryablePropertiesChecksMixin(InjectableMixin):

    # TODO: date_hierarchy

    def _check_ordering_item(self, obj, *args):
        errors = super(QueryablePropertiesChecksMixin, self)._check_ordering_item(obj, *args)
        if errors:
            # The number of arguments differs between old and recent Django
            # versions.
            field_name = args[-2]

            if not isinstance(field_name, six.string_types) and Combinable is not None:
                if isinstance(field_name, Combinable):
                    field_name = field_name.asc()
                if isinstance(field_name, OrderBy) and isinstance(field_name.expression, F):
                    field_name = field_name.expression.name
                else:
                    return errors
            if field_name.startswith('-') or field_name.startswith('+'):
                field_name = field_name[1:]
            if resolve_queryable_property(obj.model, field_name.split(LOOKUP_SEP))[0]:
                return []
        return errors


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

    def get_list_select_properties(self):
        return self.list_select_properties


class QueryablePropertiesAdmin(QueryablePropertiesAdminMixin, ModelAdmin):

    pass


class QueryablePropertiesStackedInline(QueryablePropertiesAdminMixin, StackedInline):

    pass


class QueryablePropertiesTabularInline(QueryablePropertiesAdminMixin, TabularInline):

    pass
