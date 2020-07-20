# encoding: utf-8

from __future__ import unicode_literals

from copy import deepcopy
from functools import partial

import six

from ..compat import LOOKUP_SEP
from ..exceptions import QueryablePropertyError
from ..utils import get_queryable_property, parametrizable_decorator, reset_queryable_property
from .cache_behavior import CLEAR_CACHE
from .mixins import AnnotationMixin, LookupFilterMixin

RESET_METHOD_NAME = 'reset_property'


@six.python_2_unicode_compatible
class QueryableProperty(object):
    """
    Base class for all queryable properties, which are basically simple
    descriptors with some added methods for queryset interaction.
    """

    cached = False  #: Determines if the result of the getter is cached, like Django's cached_property.
    setter_cache_behavior = CLEAR_CACHE  #: Determines what happens if the setter of a cached property is used.
    filter_requires_annotation = False  #: Determines if using the property to filter requires annotating first.

    # Set the attributes of mixin methods to None for easier checks if a
    # property implements them.
    set_value = None
    get_annotation = None
    get_update_kwargs = None

    def __init__(self):
        self.model = None
        self.name = None
        self.setter_cache_behavior = six.get_method_function(self.setter_cache_behavior)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self

        # Always check for cached values first regardless of the self.cached
        # since values will also be cached through annotations.
        if self._has_cached_value(obj):
            return self._get_cached_value(obj)
        if not self.get_value:
            raise AttributeError('Unreadable queryable property.')
        value = self.get_value(obj)
        if self.cached:
            self._set_cached_value(obj, value)
        return value

    def __set__(self, obj, value):
        if not self.set_value:
            raise AttributeError("Can't set queryable property.")
        return_value = self.set_value(obj, value)
        # If a value is set and the property is set up to cache values or has
        # a current cached value, invoke the configured setter cache behavior.
        if self.cached or self._has_cached_value(obj):
            self.setter_cache_behavior(self, obj, value, return_value)

    def __reduce__(self):
        # Since queryable property instances only make sense in the context of
        # model classes, they can simply be pickled using their model class and
        # name and loaded back from the model class when unpickling. This also
        # saves memory as unpickled properties will be the exact same object as
        # the one on the model class.
        return get_queryable_property, (self.model, self.name)

    def __str__(self):
        return '.'.join((self.model._meta.app_label, self.model._meta.object_name, self.name))

    def __repr__(self):
        return '<{}: {}>'.format(self.__class__.__name__, six.text_type(self))

    def get_value(self, obj):  # pragma: no cover
        """
        Getter method for the queryable property, which will be called when
        the property is read-accessed.

        :param django.db.models.Model obj: The object on which the property was accessed.
        :return: The getter value.
        """
        raise NotImplementedError()

    def get_filter(self, cls, lookup, value):  # pragma: no cover
        """
        Generate a :class:`django.db.models.Q` object that emulates filtering
        a queryset using this property.

        :param type cls: The model class of which a queryset should be
                         filtered.
        :param str lookup: The lookup to use for the filter (e.g. 'exact',
                           'lt', etc.)
        :param value: The value passed to the filter condition.
        :return: A Q object to filter using this property.
        :rtype: django.db.models.Q
        """
        raise NotImplementedError()

    def contribute_to_class(self, cls, name):
        if LOOKUP_SEP in name:
            raise QueryablePropertyError('The name of a queryable property must not contain the lookup separator "{}".'
                                         .format(LOOKUP_SEP))
        # Store some useful values on model class initialization.
        self.model = self.model or cls
        self.name = self.name or name
        setattr(cls, name, self)  # Re-append the property to the model class
        # If not already set, also add a method to the model class that allows
        # to reset the cached values of queryable properties.
        if not getattr(cls, RESET_METHOD_NAME, None):
            setattr(cls, RESET_METHOD_NAME, reset_queryable_property)

    def _get_cached_value(self, obj):
        """
        Get the cached value for this property from the given object. Requires
        a cached value to be present.

        :param django.db.models.Model obj: The object to get the cached value
                                           from.
        :return: The cached value.
        """
        return obj.__dict__[self.name]

    def _set_cached_value(self, obj, value):
        """
        Set the cached value for this property on the given object.

        :param django.db.models.Model obj: The object to set the cached value
                                           for.
        :param value: The value to cache.
        """
        obj.__dict__[self.name] = value

    def _has_cached_value(self, obj):
        """
        Check if a value for this property is cached on the given object.

        :param django.db.models.Model obj: The object to check for a cached
                                           value.
        :return: True if a value is cached; otherwise False.
        :rtype: bool
        """
        return self.name in obj.__dict__

    def _clear_cached_value(self, obj):
        """
        Clear the cached value for this property on the given object. Does not
        require a cached value to be present and will do nothing if no value is
        cached.

        :param django.db.models.Model obj: The object to clear the cached value
                                           on.
        """
        obj.__dict__.pop(self.name, None)


class queryable_property(QueryableProperty):
    """
    A queryable property that is intended to be used as a decorator.
    """

    # Set the attributes of the default methods to None since the decorator
    # may be used without implementing these methods.
    get_value = None
    get_filter = None

    def __init__(self, getter=None, cached=None):
        """
        Initialize a new queryable property, optionally using the given getter
        method and getter configuration.

        :param function getter: The method to decorate.
        :param cached: Determines if values obtained by the getter should be
                       cached (similar to ``cached_property``). A value of None
                       means no change.
        :type cached: bool | None
        """
        super(queryable_property, self).__init__()
        self.__doc__ = None
        if getter:
            self(getter)
        if cached is not None:
            self.cached = cached

    def __call__(self, getter):
        # Since the initializer may be used as a parametrized decorator, the
        # resulting object will be called to apply the decorator.
        self.get_value = getter
        if getter.__doc__:
            self.__doc__ = getter.__doc__
        return self

    def _extract_function(self, method_or_function):
        """
        Extract the function from the given function or method. Allows to
        decorate either regular functions or e.g. classmethods with the
        decorators of this property.

        :param method_or_function: The decorated method or function.
        :type method_or_function: function | classmethod | staticmethod
        :return: The actual function object.
        """
        return getattr(method_or_function, '__func__', method_or_function)

    def _clone(self, **kwargs):
        """
        Clone this queryable property while overriding attributes. This is
        necessary whenever an additional decorator is used to not mess up in
        inheritance scenarios.

        :param kwargs: Attributes to override.
        :return: A (modified) clone of this queryable property.
        :rtype: queryable_property
        """
        attrs = deepcopy(self.__dict__)
        attrs.update(kwargs)
        clone = self.__class__()
        clone.__dict__.update(attrs)
        return clone

    @parametrizable_decorator
    def getter(self, method, cached=None):
        """
        Decorator for a function or method that is used as the getter of this
        queryable property. May be used as a parameter-less decorator
        (``@getter``) or as a decorator with keyword arguments
        (``@getter(cached=True)``).

        :param function method: The method to decorate.
        :param cached: If True, values returned by the decorated getter method
                       will be cached. A value of None means no change.
        :type cached: bool | None
        :return: A cloned queryable property.
        :rtype: queryable_property
        """
        clone = self._clone()
        if cached is not None:
            clone.cached = cached
        return clone(method)

    @parametrizable_decorator
    def setter(self, method, cache_behavior=None):
        """
        Decorator for a function or method that is used as the setter of this
        queryable property. May be used as a parameter-less decorator
        (``@setter``) or as a decorator with keyword arguments
        (``@setter(cache_behavior=DO_NOTHING)``).

        :param function method: The method to decorate.
        :param cache_behavior: A function that defines how the setter interacts
                               with cached values. A value of None means no
                               change.
        :type cache_behavior: function | None
        :return: A cloned queryable property.
        :rtype: queryable_property
        """
        attrs = dict(set_value=method)
        if cache_behavior:
            attrs['setter_cache_behavior'] = cache_behavior
        return self._clone(**attrs)

    @parametrizable_decorator
    def filter(self, method, requires_annotation=None, lookups=None, boolean=False):
        """
        Decorator for a function or method that is used to generate a filter
        for querysets to emulate filtering by this queryable property. May be
        used as a parameter-less decorator (``@filter``) or as a decorator with
        keyword arguments (``@filter(requires_annotation=False)``). May be used
        to define a one-for-all filter function or a filter function that will
        be called for certain lookups only using the `lookups` argument.

        :param method: The method to decorate.
        :type method: function | classmethod | staticmethod
        :param requires_annotation: True if filtering using this queryable
                                    property requires its annotation to be
                                    applied first; otherwise False. None if
                                    this information should not be changed.
        :type requires_annotation: bool | None
        :param lookups: If given, the decorated function or method will be used
                        for the specified lookup(s) only. Automatically adds
                        the :class:`LookupFilterMixin` to this property if this
                        is used.
        :type lookups: collections.Iterable[str] | None
        :param boolean: If True, the decorated function or method is expected
                        to be a simple boolean filter, which doesn't take the
                        `lookup` and `value` parameters and should always
                        return a `Q` object representing the positive (i.e.
                        `True`) filter case. The decorator will automatically
                        negate the condition if the filter was called with a
                        `False` value.
        :type boolean: bool
        :return: A cloned queryable property.
        :rtype: queryable_property
        """
        method = extracted = self._extract_function(method)
        if boolean:
            if lookups is not None:
                raise QueryablePropertyError('A boolean filter cannot specify lookups at the same time.')

            # Re-use the boolean_filter decorator by simulating a method with
            # a self argument when in reality `method` doesn't have one.
            method = LookupFilterMixin.boolean_filter(lambda prop, model: extracted(model))
            lookups = method._lookups
            method = partial(method, None)

        attrs = {}
        if requires_annotation is not None:
            attrs['filter_requires_annotation'] = requires_annotation
        if lookups is not None:  # Register only for the given lookups.
            attrs['lookup_mappings'] = dict(getattr(self, 'lookup_mappings', {}),
                                            **{lookup: method for lookup in lookups})
        else:  # Register as a one-for-all filter function.
            attrs['get_filter'] = method
        clone = self._clone(**attrs)
        # If the decorated function/method is used for certain lookups only,
        # add the LookupFilterMixin into the new property to be able to reuse
        # its filter implementation based on the lookup mappings.
        if lookups is not None and not isinstance(clone, LookupFilterMixin):
            LookupFilterMixin.inject_into_object(clone)
        return clone

    def annotater(self, method):
        """
        Decorator for a function or method that is used to generate an
        annotation to represent this queryable property in querysets. The
        :class:`AnnotationMixin` will automatically applied to this property
        when this decorator is used.

        :param method: The method to decorate.
        :type method: function | classmethod | staticmethod
        :return: A cloned queryable property.
        :rtype: queryable_property
        """
        clone = self._clone(get_annotation=self._extract_function(method))
        # Dynamically add the AnnotationMixin into the new property to allow
        # to use the default filter implementation. Since an explicitly set
        # filter implementation is stored in the instance dict, it will be used
        # over the default implementation.
        if not isinstance(clone, AnnotationMixin):
            AnnotationMixin.inject_into_object(clone)
        return clone

    def updater(self, method):
        """
        Decorator for a function or method that is used to resolve an update
        keyword argument for this queryable property into the actual update
        keyword arguments.

        :param method: The method to decorate.
        :type method: function | classmethod | staticmethod
        :return: A cloned queryable property.
        :rtype: queryable_property
        """
        return self._clone(get_update_kwargs=self._extract_function(method))
