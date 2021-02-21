# -*- coding: utf-8 -*-

from itertools import chain

import six
from django.contrib.admin.options import InlineModelAdmin
from django.core.exceptions import ImproperlyConfigured
from django.db.models import DateField, expressions, F

from ..compat import checks, LOOKUP_SEP
from ..utils.internal import get_output_field, InjectableMixin, resolve_queryable_property


class Error(getattr(checks, 'Error', object)):

    def __init__(self, msg, obj, error_id):
        error_id = 'queryable_properties.admin.E{:03}'.format(error_id)
        if self.__class__.__bases__ != (object,):
            super(Error, self).__init__(msg, obj=obj, id=error_id)
        else:  # pragma: no cover
            self.msg = msg
            self.obj = obj
            self.id = error_id

    def raise_exception(self):
        raise ImproperlyConfigured('{}: ({}) {}'.format(six.text_type(self.obj), self.id, self.msg))


class QueryablePropertiesChecksMixin(InjectableMixin):

    def check(self, admin_obj, *args, **kwargs):
        errors = super(QueryablePropertiesChecksMixin, self).check(admin_obj, *args, **kwargs)
        # The number of arguments differs between old and recent Django
        # versions.
        model = getattr(admin_obj, 'model', args[0] if args else None)
        errors.extend(self._check_list_select_properties(admin_obj, model))
        return errors

    def validate(self, cls, model):  # pragma: no cover
        fake_cls = self._validate_queryable_properties(cls, model)
        super(QueryablePropertiesChecksMixin, self).validate(fake_cls, model)

    def _validate_queryable_properties(self, cls, model):  # pragma: no cover
        date_hierarchy = None
        list_filter = []
        ordering = []
        errors = self._check_list_select_properties(cls, model)
        pk_name = model._meta.pk.name

        if not issubclass(cls, InlineModelAdmin):
            if cls.date_hierarchy:
                prop, property_errors = self._check_date_hierarchy_queryable_property(cls, model)
                if prop:
                    errors.extend(property_errors)
                else:
                    date_hierarchy = cls.date_hierarchy

            for i, item in enumerate(cls.list_filter or ()):
                if not callable(item):
                    prop, property_errors = self._check_list_filter_queryable_property(cls, model, item,
                                                                                       'list_filter[{}]'.format(i))
                    if prop:
                        errors.extend(property_errors)
                        item = (pk_name, item[1]) if isinstance(item, (tuple, list)) else pk_name
                list_filter.append(item)

        for i, field_name in enumerate(cls.ordering or ()):
            prop, property_errors = self._check_ordering_queryable_property(cls, model, field_name,
                                                                            'ordering[{}]'.format(i))
            if prop:
                errors.extend(property_errors)
                field_name = pk_name
            ordering.append(field_name)

        if errors:
            errors[0].raise_exception()

        # Build a fake admin class without queryable property references to be
        # validated by Django.
        return type(cls.__name__, (cls,), {
            'date_hierarchy': date_hierarchy,
            'list_filter': list_filter,
            'ordering': ordering,
        })

    def _check_queryable_property(self, obj, model, query_path, label, allow_relation=True, allow_lookups=True):
        errors = []
        property_ref, lookups = resolve_queryable_property(model, query_path.split(LOOKUP_SEP))
        if not property_ref:
            message = '"{}" refers to "{}", which is not a queryable property.'.format(label, query_path)
            errors.append(Error(message, obj, error_id=1))
        else:
            if not property_ref.property.get_annotation:
                message = ('"{}" refers to queryable property "{}", which does not implement annotation creation.'
                           .format(label, query_path))
                errors.append(Error(message, obj, error_id=2))
            if query_path.count(LOOKUP_SEP) > len(lookups) and not allow_relation:
                message = ('The queryable property in "{}" must not be a property on a related model (invalid item: '
                           '"{}").'.format(label, query_path))
                errors.append(Error(message, obj, error_id=3))
            if lookups and not allow_lookups:
                message = ('The queryable property in "{}" must not contain lookups/transforms (invalid item: "{}").'
                           .format(label, query_path))
                errors.append(Error(message, obj, error_id=4))
        return property_ref and property_ref.property, errors

    def _check_date_hierarchy_queryable_property(self, obj, model):
        prop, property_errors = self._check_queryable_property(obj, model, obj.date_hierarchy, 'date_hierarchy')
        if prop and not property_errors:
            output_field = get_output_field(prop.get_annotation(model))
            if output_field and not isinstance(output_field, DateField):
                message = ('"date_hierarchy" refers to queryable property "{}", which does not annotate date values.'
                           .format(obj.date_hierarchy))
                property_errors.append(Error(message, obj, error_id=5))
        return prop, property_errors

    def _check_list_filter_queryable_property(self, obj, model, item, label):
        field_name = item[0] if isinstance(item, (tuple, list)) else item
        return self._check_queryable_property(obj, model, field_name, label, allow_lookups=False)

    def _check_ordering_queryable_property(self, obj, model, field_name, label):
        if not isinstance(field_name, six.string_types) and hasattr(expressions, 'Combinable'):
            if isinstance(field_name, expressions.Combinable):
                field_name = field_name.asc()
            if isinstance(field_name, expressions.OrderBy) and isinstance(field_name.expression, F):
                field_name = field_name.expression.name
        if field_name.startswith('-') or field_name.startswith('+'):
            field_name = field_name[1:]
        return self._check_queryable_property(obj, model, field_name, label)

    def _check_date_hierarchy(self, obj, *args):
        errors = super(QueryablePropertiesChecksMixin, self)._check_date_hierarchy(obj, *args)
        if not errors or errors[0].id != 'admin.E127':
            return errors

        model = args[0] if args else obj.model
        prop, property_errors = self._check_date_hierarchy_queryable_property(obj, model)
        return property_errors if prop else errors

    def _check_list_filter_item(self, obj, *args):
        errors = super(QueryablePropertiesChecksMixin, self)._check_list_filter_item(obj, *args)
        if not errors or errors[0].id != 'admin.E116':
            return errors

        # The number of arguments differs between old and recent Django
        # versions.
        model = args[0] if len(args) > 2 else obj.model
        prop, property_errors = self._check_list_filter_queryable_property(obj, model, *args[-2:])
        return property_errors if prop else errors

    def _check_ordering_item(self, obj, *args):
        errors = super(QueryablePropertiesChecksMixin, self)._check_ordering_item(obj, *args)
        if not errors or errors[0].id != 'admin.E033':
            return errors

        # The number of arguments differs between old and recent Django
        # versions.
        model = args[0] if len(args) > 2 else obj.model
        prop, property_errors = self._check_ordering_queryable_property(obj, model, *args[-2:])
        return property_errors if prop else errors

    def _check_list_select_properties(self, obj, model):
        if not isinstance(obj.list_select_properties, (list, tuple)):
            return [Error('The value of "list_select_properties" must be a list or tuple.', obj, error_id=6)]
        return list(chain.from_iterable(
            self._check_list_select_properties_item(obj, model, item, 'list_select_properties[{}]'.format(index))
            for index, item in enumerate(obj.list_select_properties)
        ))

    def _check_list_select_properties_item(self, obj, model, item, label):
        return self._check_queryable_property(obj, model, item, label, allow_relation=False, allow_lookups=False)[1]
