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


# TODO: alternative for Django < 1.6 validations
class QueryablePropertiesChecksMixin(InjectableMixin):

    def validate(self, cls, model):  # TODO: Django 1.6 to Django 1.8
        date_hierarchy = None
        list_filter = []
        ordering = []

        if cls.date_hierarchy:
            prop, property_errors = self._check_date_hierarchy_queryable_property(cls, model)
            if prop and property_errors:
                property_errors[0].raise_exception()
            elif not prop:
                date_hierarchy = cls.date_hierarchy

        for i, item in enumerate(cls.list_filter or ()):
            prop, property_errors = self._check_list_filter_queryable_property(cls, model, item,
                                                                               'list_filter[{}]'.format(i))
            if prop and property_errors:
                property_errors[0].raise_exception()
            list_filter.append('pk' if prop else item)

        for i, field_name in enumerate(cls.ordering or ()):
            prop, property_errors = self._check_ordering_queryable_property(cls, model, field_name,
                                                                            'ordering[{}]'.format(i))
            if prop and property_errors:
                property_errors[0].raise_exception()
            ordering.append('pk' if prop else field_name)

        # Build a fake admin class without queryable property references to be
        # validated by Django.
        fake_cls = type(cls.__name__, (cls,), {
            'date_hierarchy': date_hierarchy,
            'list_filter': list_filter,
            'ordering': ordering,
        })
        super(QueryablePropertiesChecksMixin, self).validate(fake_cls, model)

    def _check_queryable_property(self, obj, model, query_path, label, allow_lookups=True):
        errors = []
        property_ref, lookups = resolve_queryable_property(model, query_path.split(LOOKUP_SEP))
        if not property_ref.property.get_annotation:
            message = '"{}" refers to queryable property "{}", which does not implement annotation creation.'.format(
                label, query_path)
            errors.append(Error(message, obj, error_id=1))
        if lookups and not allow_lookups:
            message = 'Queryable properties in "{}" must not contain lookups/transforms (invalid item: "{}").'.format(
                label, query_path)
            errors.append(Error(message, obj, error_id=2))
        return property_ref and property_ref.property, errors

    def _check_date_hierarchy_queryable_property(self, obj, model):
        prop, property_errors = self._check_queryable_property(obj, model, obj.date_hierarchy, 'date_hierarchy')
        if prop and not property_errors:
            output_field = get_output_field(prop.get_annotation(model))
            if output_field and not isinstance(output_field, DateField):
                message = ('"date_hierarchy" refers to queryable property "{}", which does not annotate date values.'
                           .format(obj.date_hierarchy))
                property_errors.append(Error(message, obj, error_id=3))
        return prop, property_errors

    def _check_list_filter_queryable_property(self, obj, model, item, label):
        field_name = item[0] if isinstance(item, (tuple, list)) else item
        return self._check_queryable_property(obj, model, field_name, label, allow_lookups=False)

    def _check_ordering_queryable_property(self, obj, model, field_name, label):
        if not isinstance(field_name, six.string_types) and Combinable is not None:
            if isinstance(field_name, Combinable):
                field_name = field_name.asc()
            if isinstance(field_name, OrderBy) and isinstance(field_name.expression, F):
                field_name = field_name.expression.name
        if field_name.startswith('-') or field_name.startswith('+'):
            field_name = field_name[1:]
        return self._check_queryable_property(obj, model, field_name, label)

    def _check_date_hierarchy(self, obj):
        errors = super(QueryablePropertiesChecksMixin, self)._check_date_hierarchy(obj)
        if not errors or errors[0].id != 'admin.E127':
            return errors

        prop, property_errors = self._check_date_hierarchy_queryable_property(obj, obj.model)
        return property_errors if prop else errors

    def _check_list_filter_item(self, obj, *args):
        errors = super(QueryablePropertiesChecksMixin, self)._check_list_filter_item(obj, *args)
        if not errors or errors[0].id != 'admin.E116':
            return errors

        # The number of arguments differs between old and recent Django
        # versions.
        prop, property_errors = self._check_list_filter_queryable_property(obj, obj.model, *args[-2:])
        return property_errors if prop else errors

    def _check_ordering_item(self, obj, *args):
        errors = super(QueryablePropertiesChecksMixin, self)._check_ordering_item(obj, *args)
        if not errors or errors[0].id != 'admin.E033':
            return errors

        # The number of arguments differs between old and recent Django
        # versions.
        prop, property_errors = self._check_ordering_queryable_property(obj, obj.model, *args[-2:])
        return property_errors if prop else errors
