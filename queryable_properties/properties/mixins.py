# encoding: utf-8

from functools import wraps

import six
from django.db.models import Q

from ..compat import LOOKUP_SEP
from ..exceptions import QueryablePropertyError
from ..utils.internal import InjectableMixin


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
        boolean filters (i.e. the filter can only be called with a `True` or
        `False` value). This automatically restricts the usable lookups to
        `exact`. Decorated methods should not expect the `lookup` and `value`
        parameters and should always return a `Q` object representing the
        positive (i.e. `True`) filter case. The decorator will automatically
        negate the condition if the filter was called with a `False` value.

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
        method = self.lookup_mappings.get(lookup)
        if not method:
            raise QueryablePropertyError(
                'Queryable property "{prop}" does not implement filtering with lookup "{lookup}".'
                .format(prop=self, lookup=lookup)
            )
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
        return Q(**{LOOKUP_SEP.join((self.name, lookup)): value})


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
        queryset = self.get_queryset_for_object(obj).distinct()
        queryset = queryset.annotate(**{self.name: self.get_annotation(obj.__class__)})
        return queryset.values_list(self.name, flat=True).get()

    def get_queryset(self, model):
        """
        Construct a base queryset for the given model class that can be used
        to build queries in property code.

        :param model: The model class to build the queryset for.
        """
        return model._base_manager.all()

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
