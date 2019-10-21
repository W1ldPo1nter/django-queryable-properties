# encoding: utf-8

import six
from django.db.models import Q

from ..compat import LOOKUP_SEP
from ..exceptions import QueryablePropertyError
from ..utils import InjectableMixin


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

    def get_filter(self, cls, lookup, value):
        method = self.lookup_mappings.get(lookup)
        if not method:
            raise QueryablePropertyError(
                'Queryable property "{prop}" does not implement filtering with lookup "{lookup}".'
                .format(prop=self, lookup=lookup)
            )
        return method(cls, lookup, value)


# Alias to allow the usage of the decorator without the "LookupFilterMixin."
# prefix.
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
