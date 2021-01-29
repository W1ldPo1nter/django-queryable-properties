# -*- coding: utf-8 -*-

import six
from django.contrib.admin import ModelAdmin, StackedInline, TabularInline
from django.contrib.admin.options import BaseModelAdmin
from django.core.exceptions import ImproperlyConfigured
from django.db.models import DateField, F

try:
    from django.core.checks import Error as BaseError
except ImportError:
    BaseError = object

try:
    from django.db.models.expressions import Combinable, OrderBy
except ImportError:
    Combinable = OrderBy = None

from .compat import chain_queryset, LOOKUP_SEP
from .managers import QueryablePropertiesQuerySetMixin
from .utils.internal import InjectableMixin, resolve_queryable_property


class Error(BaseError):

    def __init__(self, msg, obj, error_id):
        error_id = 'queryable_properties.admin.E{:03}'.format(error_id)
        if BaseError is not object:
            super(Error, self).__init__(msg, obj=obj, id=error_id)
        else:
            self.msg = msg
            self.obj = obj
            self.error_id = error_id

    def raise_exception(self):
        raise ImproperlyConfigured('{}: ({}) {}'.format(six.text_type(self.obj), self.error_id, self.msg))


# TODO: alternative for Django < 1.9 validators
class QueryablePropertiesChecksMixin(InjectableMixin):

    def _check_queryable_property(self, obj, field_name, attribute_name, allow_relation=True):
        errors = []
        path = field_name.split(LOOKUP_SEP) if allow_relation else [field_name]
        property_ref = resolve_queryable_property(obj.model, path)[0]
        if not property_ref.property.get_annotation:
            message = '"{}" refers to queryable property "{}", which does not implement annotation creation.'.format(
                attribute_name, field_name)
            errors.append(Error(message, obj, error_id=1))
        return property_ref and property_ref.property, errors

    def _check_date_hierarchy(self, obj):
        errors = super(QueryablePropertiesChecksMixin, self)._check_date_hierarchy(obj)
        if not errors:
            return errors

        prop, property_errors = self._check_queryable_property(obj, obj.date_hierarchy, 'date_hierarchy')
        if prop and not property_errors:
            output_field = getattr(prop.get_annotation(obj.model), 'output_field', None)
            if output_field and not isinstance(output_field, DateField):
                message = ('"date_hierarchy" refers to queryable property "{}", which does not annotate date values.'
                           .format(obj.date_hierarchy))
                property_errors.append(Error(message, obj, error_id=2))
        return property_errors if prop else errors

    def _check_ordering_item(self, obj, *args):
        errors = super(QueryablePropertiesChecksMixin, self)._check_ordering_item(obj, *args)
        if not errors:
            return errors

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
        prop, property_errors = self._check_queryable_property(obj, field_name, 'ordering')
        return property_errors if prop else errors


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
