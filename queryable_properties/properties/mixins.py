# encoding: utf-8

from functools import wraps

import six
from django.db.models import BooleanField

from ..exceptions import QueryablePropertyError
from ..managers import QueryablePropertiesQuerySetMixin
from ..utils.internal import InjectableMixin, QueryPath

REMAINING_LOOKUPS = '*'  #: A Constant that can be used instead of lookup names to match all remaining lookups.


class LookupFilterMeta(type):
    """
    Metaclass for classes that use the :class:`LookupFilterMixin` to detect the
    individual registered filter methods and make them available to the main
    filter method.
    """

    def __new__(mcs, name, bases, attrs):
        # Find all methods that have been marked with lookups via the
        # `lookup_filter` decorator.
        mappings = {}
        for attr_name, attr in six.iteritems(attrs):
            if callable(attr) and hasattr(attr, '_lookups'):
                for lookup in attr._lookups:
                    mappings[lookup] = attr_name

        # Let the class construction take care of the lookup mappings of the
        # base class(es) and add the ones from the current class to them.
        cls = super(LookupFilterMeta, mcs).__new__(mcs, name, bases, attrs)
        cls._lookup_mappings = dict(cls._lookup_mappings, **mappings)
        return cls


class LookupFilterMixin(six.with_metaclass(LookupFilterMeta, InjectableMixin)):
    """
    A mixin for queryable properties that allows to implement queryset
    filtering via individual methods for different lookups.
    """

    # Avoid overriding the __reduce__ implementation of queryable properties.
    _dynamic_pickling = False

    # Stores mappings of lookups to the names of their corresponding filter
    # functions.
    _lookup_mappings = {}

    remaining_lookups_via_parent = False

    def __init__(self, *args, **kwargs):
        self.lookup_mappings = {lookup: getattr(self, name) for lookup, name in six.iteritems(self._lookup_mappings)}
        super(LookupFilterMixin, self).__init__(*args, **kwargs)

    @classmethod
    def lookup_filter(cls, *lookups):
        """
        Decorator for individual filter methods of classes that use the
        :class:`LookupFilterMixin` to register the decorated methods for the
        given lookups.

        :param str lookups: The lookups to register the decorated method for.
        :return: The actual internal decorator.
        :rtype: function
        """
        def decorator(func):
            func._lookups = lookups  # Store the lookups on the function to be able to read them in the meta class.
            return func
        return decorator

    @classmethod
    def boolean_filter(cls, method):
        """
        Decorator for individual filter methods of classes that use the
        :class:`LookupFilterMixin` to register the methods that are simple
        boolean filters (i.e. the filter can only be called with a ``True`` or
        ``False`` value). This automatically restricts the usable lookups to
        ``exact``. Decorated methods should not expect the ``lookup`` and
        ``value`` parameters and should always return a ``Q`` object
        representing the positive (i.e. ``True``) filter case. The decorator
        will automatically negate the condition if the filter was called with a
        ``False`` value.

        :param function method: The method to decorate.
        :return: The decorated method.
        :rtype: function
        """
        @wraps(method)
        def filter_wrapper(self, model, lookup, value):
            """Actual filter method that negates the condition if required."""
            condition = method(self, model)
            if not value:
                condition.negate()
            return condition
        lookup_decorator = cls.lookup_filter('exact')
        return lookup_decorator(filter_wrapper)

    def get_filter(self, cls, lookup, value):
        # Resolve the correct method to call for the given lookup in this order:
        # 1. Check if there is an explicit method for the given lookup.
        # 2. Check if a method is configured for REMAINING_LOOKUPS.
        # 3. Check if a fallback to the parent class implementation is allowed.
        method = self.lookup_mappings.get(lookup) or self.lookup_mappings.get(REMAINING_LOOKUPS)
        if not method:
            if not self.remaining_lookups_via_parent:
                raise QueryablePropertyError(
                    'Queryable property "{prop}" does not implement filtering with lookup "{lookup}".'
                    .format(prop=self, lookup=lookup)
                )
            method = super(LookupFilterMixin, self).get_filter
        return method(cls, lookup, value)


# Aliases to allow the usage of the decorators without the "LookupFilterMixin."
# prefix.
boolean_filter = LookupFilterMixin.boolean_filter
lookup_filter = LookupFilterMixin.lookup_filter


class SetterMixin(object):
    """
    A mixin for queryable properties that also define a setter.
    """

    def set_value(self, obj, value):  # pragma: no cover
        """
        Setter method for the queryable property, which will be called when the
        property is write-accessed.

        :param django.db.models.Model obj: The object on which the property was
                                           accessed.
        :param value: The value to set.
        """
        raise NotImplementedError()


class AnnotationMixin(InjectableMixin):
    """
    A mixin for queryable properties that allows to add an annotation to
    represent them to querysets.
    """

    # Avoid overriding the __reduce__ implementation of queryable properties.
    _dynamic_pickling = False

    filter_requires_annotation = True

    @property
    def admin_order_field(self):
        """
        Return the field name for the ordering in the admin, which is simply
        the property's name since it's annotatable.

        :return: The field name for ordering in the admin.
        :rtype: str
        """
        return self.name

    def get_annotation(self, cls):  # pragma: no cover
        """
        Construct an annotation representing this property that can be added
        to querysets of the model associated with this property.

        :param type cls: The model class of which a queryset should be
                         annotated.
        :return: An annotation object.
        """
        raise NotImplementedError()

    def get_filter(self, cls, lookup, value):
        # Since annotations can be filtered like regular fields, a Q object
        # that simply passes the filter through can be used.
        return (QueryPath(self.name) + lookup).build_filter(value)


class AnnotationGetterMixin(AnnotationMixin):
    """
    A mixin for queryable properties that support annotation and use their
    annotation even to provide the value for their getter (i.e. perform a query
    to retrieve the getter value).
    """

    def __init__(self, cached=None, *args, **kwargs):
        """
        Initialize a new queryable property based that uses the
        :class:`AnnotationGetterMixin`.

        :param cached: Determines if values obtained by the getter should be
                       cached (similar to ``cached_property``). A value of None
                       means using the default value.
        """
        super(AnnotationGetterMixin, self).__init__(*args, **kwargs)
        if cached is not None:
            self.cached = cached

    def get_value(self, obj):
        queryset = self.get_queryset_for_object(obj).distinct().select_properties(self.name)
        return queryset.values_list(self.name, flat=True).get()

    def get_queryset(self, model):
        """
        Construct a base queryset for the given model class that can be used
        to build queries in property code.

        :param model: The model class to build the queryset for.
        """
        # Inject the mixin to be able to use select_properties in the getter.
        return QueryablePropertiesQuerySetMixin.inject_into_object(model._base_manager.all())

    def get_queryset_for_object(self, obj):
        """
        Construct a base queryset that can be used to retrieve the getter value
        for the given object.

        :param django.db.models.Model obj: The object to build the queryset
                                           for.
        :return: A base queryset for the correct model that is already filtered
                 for the given object.
        :rtype: django.db.models.QuerySet
        """
        return self.get_queryset(obj.__class__).filter(pk=obj.pk)


class UpdateMixin(object):
    """
    A mixin for queryable properties that allows to use themselves in update
    queries.
    """

    def get_update_kwargs(self, cls, value):  # pragma: no cover
        """
        Resolve an update keyword argument for this property into the actual
        keyword arguments to emulate an update using this property.

        :param type cls: The model class of which an update query should be
                         performed.
        :param value: The value passed to the update call for this property.
        :return: The actual keyword arguments to set in the update call instead
                 of the given one.
        :rtype: dict
        """
        raise NotImplementedError()


class BooleanMixin(LookupFilterMixin):
    """
    Internal mixin class for common properties that return boolean values,
    which is intended to be used in conjunction with one of the annotation
    mixins.
    """

    filter_requires_annotation = False

    def _get_condition(self, cls):  # pragma: no cover
        """
        Build the query filter condition for this boolean property, which is
        used for both the filter and the annotation implementation.

        :param type cls: The model class of which a queryset should be filtered
                         or annotated.
        :return: The filter condition for this property.
        :rtype: django.db.models.Q
        """
        raise NotImplementedError()

    @boolean_filter
    def get_exact_filter(self, cls):
        return self._get_condition(cls)

    def get_annotation(self, cls):
        from django.db.models import Case, When

        return Case(
            When(self._get_condition(cls), then=True),
            default=False,
            output_field=BooleanField()
        )


class SubqueryMixin(AnnotationGetterMixin):
    """
    Internal mixin class for common properties that are based on custom
    subqueries.
    """

    def __init__(self, queryset, **kwargs):
        """
        Initialize a new subquery-based queryable property.

        :param queryset: The internal queryset to use as the subquery or a
                         callable without arguments that generates the internal
                         queryset.
        :type queryset: django.db.models.QuerySet | function
        """
        self.queryset = queryset
        super(SubqueryMixin, self).__init__(**kwargs)

    def _build_subquery(self, queryset):  # pragma: no cover
        """
        Build the subquery annotation that should be used to represent this
        queryable property in querysets.

        :param django.db.models.QuerySet queryset: The internal queryset to
                                                   base the annotation on.
        :return: The subquery annotation.
        :rtype: django.db.models.expressions.Subquery
        """
        raise NotImplementedError()

    def get_annotation(self, cls):
        queryset = self.queryset
        if callable(queryset):
            queryset = queryset()
        return self._build_subquery(queryset)
