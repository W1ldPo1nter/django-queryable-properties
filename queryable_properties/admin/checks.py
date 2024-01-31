from itertools import chain

from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.db.models import F, expressions

from ..utils.internal import InjectableMixin, QueryPath, resolve_queryable_property


class Error(checks.Error):
    """
    Custom error class to normalize check/validation error handling across
    all supported Django version. Also takes care of producing correct
    queryable properties error IDs and raising exceptions for old-style
    validations.
    """

    def __init__(self, msg, obj, error_id):
        """
        Initialize a new error object with the given data.

        :param str msg: The error message.
        :param obj: The object which was checked/validated.
        :param int error_id: A unique ID for the error.
        """
        error_id = 'queryable_properties.admin.E{:03}'.format(error_id)
        super().__init__(msg, obj=obj, id=error_id)

    def raise_exception(self):
        """Raise an ImproperlyConfigured exception for this error."""
        raise ImproperlyConfigured('{}: ({}) {}'.format(str(self.obj), self.id, self.msg))


class QueryablePropertiesChecksMixin(InjectableMixin):
    """
    A mixin for Django's recent admin checks classes as well as old-style
    validation classes that allows to validate references to queryable
    properties in admin class attributes.
    """

    def check(self, admin_obj, *args, **kwargs):
        errors = super().check(admin_obj, *args, **kwargs)
        # The number of arguments differs between old and recent Django
        # versions.
        model = getattr(admin_obj, 'model', args[0] if args else None)
        errors.extend(self._check_list_select_properties(admin_obj, model))
        return errors

    def _check_queryable_property(self, obj, model, query_path, label, allow_relation=True, allow_lookups=True):
        """
        Perform common checks for a (potential) referenced queryable property.

        :param obj: The admin object or class.
        :param model: The model the admin class is used for.
        :param QueryPath query_path: The query path to the queryable property.
        :param str label: A label to use for error messages.
        :param bool allow_relation: Whether or not the queryable property
                                    should be considered valid if it is
                                    reached via relations.
        :param bool allow_lookups: Whether or not the reference to the
                                   queryable property may contain lookups.
        :return: A 2-tuple containing the resolved queryable property (if any)
                 as well as a list of check errors.
        :rtype: (queryable_properties.properties.QueryableProperty, list[Error])
        """
        errors = []
        property_ref, lookups = resolve_queryable_property(model, query_path)
        if not property_ref:
            message = '"{}" refers to "{}", which is not a queryable property.'.format(label, query_path)
            errors.append(Error(message, obj, error_id=1))
        else:
            if not property_ref.property.get_annotation:
                message = ('"{}" refers to queryable property "{}", which does not implement annotation creation.'
                           .format(label, query_path))
                errors.append(Error(message, obj, error_id=2))
            if len(query_path) > len(lookups) + 1 and not allow_relation:
                message = ('The queryable property in "{}" must not be a property on a related model (invalid item: '
                           '"{}").'.format(label, query_path))
                errors.append(Error(message, obj, error_id=3))
            if lookups and not allow_lookups:
                message = ('The queryable property in "{}" must not contain lookups/transforms (invalid item: "{}").'
                           .format(label, query_path))
                errors.append(Error(message, obj, error_id=4))
        return property_ref and property_ref.property, errors

    def _check_list_filter_queryable_property(self, obj, model, item, label):
        """
        Perform checks for a (potential) queryable property used as a list
        filter item.

        :param obj: The admin object or class.
        :param model: The model the admin class is used for.
        :param str | list | tuple item: The list filter item.
        :param str label: A label to use for error messages.
        :return: A 2-tuple containing the resolved queryable property (if any)
                 as well as a list of check errors.
        :rtype: (queryable_properties.properties.QueryableProperty, list[Error])
        """
        field_name = item[0] if isinstance(item, (tuple, list)) else item
        return self._check_queryable_property(obj, model, QueryPath(field_name), label, allow_lookups=False)

    def _check_ordering_queryable_property(self, obj, model, field_name, label):
        """
        Perform checks for a (potential) queryable property used as an ordering
        item.

        :param obj: The admin object or class.
        :param model: The model the admin class is used for.
        :param str | expressions.BaseExpression field_name: The ordering item.
        :param str label: A label to use for error messages.
        :return: A 2-tuple containing the resolved queryable property (if any)
                 as well as a list of check errors.
        :rtype: (queryable_properties.properties.QueryableProperty, list[Error])
        """
        if not isinstance(field_name, str) and hasattr(expressions, 'Combinable'):
            if isinstance(field_name, expressions.Combinable):
                field_name = field_name.asc()
            if isinstance(field_name, expressions.OrderBy) and isinstance(field_name.expression, F):
                field_name = field_name.expression.name
        if field_name.startswith('-') or field_name.startswith('+'):
            field_name = field_name[1:]
        return self._check_queryable_property(obj, model, QueryPath(field_name), label)

    def _check_list_filter_item(self, obj, *args):
        errors = super()._check_list_filter_item(obj, *args)
        if not errors or errors[0].id != 'admin.E116':
            return errors

        # The number of arguments differs between old and recent Django
        # versions.
        model = args[0] if len(args) > 2 else obj.model
        prop, property_errors = self._check_list_filter_queryable_property(obj, model, *args[-2:])
        return property_errors if prop else errors

    def _check_ordering_item(self, obj, *args):
        errors = super()._check_ordering_item(obj, *args)
        if not errors or errors[0].id != 'admin.E033':
            return errors

        # The number of arguments differs between old and recent Django
        # versions.
        model = args[0] if len(args) > 2 else obj.model
        prop, property_errors = self._check_ordering_queryable_property(obj, model, *args[-2:])
        return property_errors if prop else errors

    def _check_list_select_properties(self, obj, model):
        """
        Perform checks for the `list_select_properties` value as a whole.

        :param obj: The admin object or class.
        :param model: The model the admin class is used for.
        :return: A 2-tuple containing the resolved queryable property (if any)
                 as well as a list of check errors.
        :rtype: (queryable_properties.properties.QueryableProperty, list[Error])
        """
        if not isinstance(obj.list_select_properties, (list, tuple)):
            return [Error('The value of "list_select_properties" must be a list or tuple.', obj, error_id=5)]
        return list(chain.from_iterable(
            self._check_list_select_properties_item(obj, model, item, 'list_select_properties[{}]'.format(index))
            for index, item in enumerate(obj.list_select_properties)
        ))

    def _check_list_select_properties_item(self, obj, model, item, label):
        """
        Perform checks for a (potential) queryable property used as a
        `list_select_properties` item.

        :param obj: The admin object or class.
        :param model: The model the admin class is used for.
        :param str item: The list_select_properties item.
        :param str label: A label to use for error messages.
        :return: A 2-tuple containing the resolved queryable property (if any)
                 as well as a list of check errors.
        :rtype: (queryable_properties.properties.QueryableProperty, list[Error])
        """
        return self._check_queryable_property(obj, model, QueryPath(item), label,
                                              allow_relation=False, allow_lookups=False)[1]
