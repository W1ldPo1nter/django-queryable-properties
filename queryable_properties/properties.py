# encoding: utf-8

from __future__ import unicode_literals

from django.db.models import Q
from django.utils import six

from .compat import LOOKUP_SEP
from .utils import get_queryable_property, reset_queryable_property

RESET_METHOD_NAME = 'reset_property'


def CLEAR_CACHE(prop, obj, value, return_value):
    """
    Setter cache behavior function that will clear the cached value for a
    cached queryable property on objects after the setter was used.

    :param QueryableProperty prop: The property whose setter was used.
    :param django.db.models.Model obj: The object the setter was used on.
    :param value: The value that was passed to the setter.
    :param return_value: The return value of the setter function/method.
    """
    prop._clear_cached_value(obj)


def CACHE_VALUE(prop, obj, value, return_value):
    """
    Setter cache behavior function that will update the cache for the cached
    queryable property on the object in question with the (raw) value that was
    passed to the setter.

    :param QueryableProperty prop: The property whose setter was used.
    :param django.db.models.Model obj: The object the setter was used on.
    :param value: The value that was passed to the setter.
    :param return_value: The return value of the setter function/method.
    """
    prop._set_cached_value(obj, value)


def CACHE_RETURN_VALUE(prop, obj, value, return_value):
    """
    Setter cache behavior function that will update the cache for the cached
    queryable property on the object in question with the return value of the
    setter function/method.

    :param QueryableProperty prop: The property whose setter was used.
    :param django.db.models.Model obj: The object the setter was used on.
    :param value: The value that was passed to the setter.
    :param return_value: The return value of the setter function/method.
    """
    prop._set_cached_value(obj, return_value)


def DO_NOTHING(prop, obj, value, return_value):
    """
    Setter cache behavior function that will do nothing after the setter of
    a cached queryable property was used, retaining previously cached values.

    :param QueryableProperty prop: The property whose setter was used.
    :param django.db.models.Model obj: The object the setter was used on.
    :param value: The value that was passed to the setter.
    :param return_value: The return value of the setter function/method.
    """
    pass


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


class AnnotationMixin(object):
    """
    A mixin for queryable properties that allow to add an annotation to
    represent them to querysets.
    """

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
    A mixin for queryable properties that allow to use themselves in update
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


class queryable_property(QueryableProperty):
    """
    A queryable property that is intended to be used like regular properties,
    e.g. as decorator.
    """

    # Set the attributes of the default methods to None since the decorator
    # may be used without implementing these methods.
    get_value = None
    get_filter = None

    def __init__(self, getter=None, setter=None, filter=None, annotater=None, updater=None,
                 cached=False, setter_cache_behavior=CLEAR_CACHE, filter_requires_annotation=None, doc=None):
        """
        Initialize a new queryable property using the given methods, which may
        be regular functions or classmethods.

        :param getter: The getter function/method for the property.
        :param setter: The setter function/method for the property.
        :param filter: The filter function/method for the property
                       (see :meth:`QueryableProperty.get_filter`).
        :param annotater: The annotation function/method for the property
                          (see :meth:`QueryableProperty.get_annotation`).
        :param updater: The update function/method for the property
                        (see :meth:`QueryableProperty.get_update_kwargs`).
        :param bool cached: Determines if values obtained by the getter should
                            be cached (like Django's cached_property).
        :param setter_cache_behavior: A function that defines how the setter
                                      interacts with cached values.
        :param bool filter_requires_annotation: Determines if using the
                                                property to filter requires
                                                annotating first.
        :param doc: The docstring for this property. If set to None (default),
                    the docstring of the getter will be used (if any).
        """
        super(queryable_property, self).__init__()
        if getter:
            self.get_value = getter
            if doc is None:
                doc = getter.__doc__
        if setter:
            self.set_value = setter
        if filter:
            self.get_filter = self._extract_function(filter)
            # The filter function may be automatically set to the get_filter
            # method of the AnnotationMixin, in which case the method has to
            # be bound to the current instance.
            if self.get_filter is self._extract_function(AnnotationMixin.get_filter):
                self.get_filter = six.create_bound_method(self.get_filter, self)
        if annotater:
            self.get_annotation = self._extract_function(annotater)
        if updater:
            self.get_update_kwargs = self._extract_function(updater)
        self.cached = cached
        self.setter_cache_behavior = setter_cache_behavior
        # Use None as a default value for filter_requires_annotation to
        # distinct between a "default False" (None) and an explicit False set
        # by the implementation.
        self.filter_requires_annotation = filter_requires_annotation
        self.__doc__ = doc

    def __call__(self, getter):
        # Since the initializer may be used as a parametrized decorator, the
        # resulting object will be called to apply the decorator.
        return self.getter(getter)

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
        defaults = dict(
            getter=self.__dict__.get('get_value'),
            setter=self.__dict__.get('set_value'),
            filter=self.__dict__.get('get_filter'),
            annotater=self.__dict__.get('get_annotation'),
            updater=self.__dict__.get('get_update_kwargs'),
            cached=self.cached,
            setter_cache_behavior=self.setter_cache_behavior,
            filter_requires_annotation=self.filter_requires_annotation,
            doc=self.__doc__
        )
        defaults.update(kwargs)
        return self.__class__(**defaults)

    def getter(self, method=None, cached=False):
        """
        Decorator for a function or method that is used as the getter of this
        queryable property. May be used as a parameter-less decorator
        (``@getter``) or as a decorator with keyword args
        (``@getter(cached=True)``).

        :param method: The method to decorate. If it is None, the parameterized
                       usage of this decorator is assumed, so this method
                       returns the actual decorator function.
        :type method: function | classmethod | staticmethod
        :param bool cached: If True, values returned by the decorated getter
                            method will be cached.
        :return: A cloned queryable property or the actual decorator function.
        :rtype: queryable_property | function
        """
        if not method:
            def decorator(meth):
                return self._clone(getter=meth, cached=cached)
            return decorator
        return self._clone(getter=method)

    def setter(self, method=None, cache_behavior=CLEAR_CACHE):
        """
        Decorator for a function or method that is used as the setter of this
        queryable property. May be used as a parameter-less decorator
        (``@setter``) or as a decorator with keyword args
        (``@setter(cache_behavior=DO_NOTHING)``).

        :param method: The method to decorate.
        :type method: function | classmethod | staticmethod
        :param function cache_behavior: A function that defines how the setter
                                        interacts with cached values.
        :return: A cloned queryable property.
        :rtype: queryable_property
        """
        if not method:
            def decorator(meth):
                return self._clone(setter=meth, setter_cache_behavior=cache_behavior)
            return decorator
        return self._clone(setter=method)

    def filter(self, method=None, requires_annotation=None):
        """
        Decorator for a function or method that is used to generate a filter
        for querysets to emulate filtering by this queryable property. May be
        used as a parameter-less decorator (``@filter``) or as a decorator with
        keyword args (``@filter(requires_annotation=False)``).

        :param method: The method to decorate. If it is None, the parameterized
                       usage of this decorator is assumed, so this method
                       returns the actual decorator function.
        :type method: function | classmethod | staticmethod
        :param requires_annotation: True if filtering using this queryable
                                    property requires its annotation to be
                                    applied first; otherwise False. None if
                                    this information should not be changed.
        :type requires_annotation: bool | None
        :return: A cloned queryable property or the actual decorator function.
        :rtype: queryable_property | function
        """
        if not method:
            def decorator(meth):
                annotation_req = self.filter_requires_annotation if requires_annotation is None else requires_annotation
                return self._clone(filter=meth, filter_requires_annotation=annotation_req)
            return decorator
        return self._clone(filter=method)

    def annotater(self, method):
        """
        Decorator for a function or method that is used to generate an
        annotation to represent this queryable property in querysets.

        :param method: The method to decorate.
        :type method: function | classmethod | staticmethod
        :return: A cloned queryable property.
        :rtype: queryable_property
        """
        kwargs = {'annotater': method}
        # If an annotater is defined but a filter isn't, use the default filter
        # implementation based on an annotation from the AnnotationMixin. This
        # way, all properties defining an annotater are automatically
        # filterable while still having the option to register a custom filter
        # method.
        if not self.get_filter:
            kwargs['filter'] = AnnotationMixin.get_filter
        # If no value was explicitly set for filter_requires_annotation, set it
        # to True since the default filter implementation of the
        # AnnotationMixin acts the same way.
        if self.filter_requires_annotation is None:
            kwargs['filter_requires_annotation'] = True
        return self._clone(**kwargs)

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
        return self._clone(updater=method)
