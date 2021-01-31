# -*- coding: utf-8 -*-

import six
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

from ..compat import LOOKUP_SEP
from ..utils.internal import get_output_field, InjectableMixin, resolve_queryable_property


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

    def _check_queryable_property(self, obj, query_path, attribute_name, allow_lookups=True):
        errors = []
        property_ref, lookups = resolve_queryable_property(obj.model, query_path.split(LOOKUP_SEP))
        if not property_ref.property.get_annotation:
            message = '"{}" refers to queryable property "{}", which does not implement annotation creation.'.format(
                attribute_name, query_path)
            errors.append(Error(message, obj, error_id=1))
        if lookups and not allow_lookups:
            message = 'Queryable properties in "{}" must not contain lookups/transforms (invalid item: "{}").'.format(
                attribute_name, query_path)
            errors.append(Error(message, obj, error_id=2))
        return property_ref and property_ref.property, errors

    def _check_date_hierarchy(self, obj):
        errors = super(QueryablePropertiesChecksMixin, self)._check_date_hierarchy(obj)
        if not errors or errors[0].id != 'admin.E127':
            return errors

        prop, property_errors = self._check_queryable_property(obj, obj.date_hierarchy, 'date_hierarchy')
        if prop and not property_errors:
            output_field = get_output_field(prop.get_annotation(obj.model))
            if output_field and not isinstance(output_field, DateField):
                message = ('"date_hierarchy" refers to queryable property "{}", which does not annotate date values.'
                           .format(obj.date_hierarchy))
                property_errors.append(Error(message, obj, error_id=3))
        return property_errors if prop else errors

    def _check_list_filter_item(self, obj, *args):
        errors = super(QueryablePropertiesChecksMixin, self)._check_list_filter_item(obj, *args)
        if not errors or errors[0].id != 'admin.E116':
            return errors

        # The number of arguments differs between old and recent Django
        # versions.
        item = args[-2]
        field_name = item[0] if isinstance(item, (tuple, list)) else item
        prop, property_errors = self._check_queryable_property(obj, field_name, 'list_filter', allow_lookups=False)
        return property_errors if prop else errors

    def _check_ordering_item(self, obj, *args):
        errors = super(QueryablePropertiesChecksMixin, self)._check_ordering_item(obj, *args)
        if not errors or errors[0].id != 'admin.E033':
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
