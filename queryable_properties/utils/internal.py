# -*- coding: utf-8 -*-
"""
Internal utilities used by the queryable properties library, which may change
without notice or be removed without deprecation.
"""

from collections import namedtuple
from copy import deepcopy
from functools import wraps

import six
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Manager, Q
from django.utils.decorators import method_decorator
from django.utils.tree import Node

from ..compat import LOOKUP_SEP, get_related_model
from ..exceptions import FieldDoesNotExist, QueryablePropertyDoesNotExist, QueryablePropertyError

MISSING_OBJECT = object()  #: Arbitrary object to represent that an object in an attribute chain is missing.


@six.python_2_unicode_compatible
class QueryPath(tuple):
    """
    A utility class to represent query paths, i.e. paths using Django's
    LOOKUP_SEP as their separator.

    Objects can be used to build the string representation of a query path and
    to combine paths using the ``+`` operator.
    """
    __slots__ = ()

    def __new__(cls, path=()):
        """
        Build a new query path instance using the given path, which may be
        either a string that will be split up using the LOOKUP_SEP or another
        type of iterable that already contains the individual path parts.

        :param collections.Iterable path: The query path to represent as string
                                          or other iterable.
        """
        if isinstance(path, six.string_types):
            path = path.split(LOOKUP_SEP)
        return super(QueryPath, cls).__new__(cls, path)

    def __add__(self, other):
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        return self.__class__(tuple(self) + tuple(other))

    def __getitem__(self, item):
        result = super(QueryPath, self).__getitem__(item)
        if isinstance(item, slice):
            result = self.__class__(result)
        return result

    def __getslice__(self, i, j):  # pragma: no cover
        return self.__class__(super(QueryPath, self).__getslice__(i, j))

    def __str__(self):
        return LOOKUP_SEP.join(self)

    def __repr__(self):
        return '<{}: {}>'.format(self.__class__.__name__, six.text_type(self))

    def build_filter(self, value):
        """
        Build a filter condition based on this query path and the given value.

        :param value: The value to filter against.
        :return: The filter condition as a Q object.
        :rtype: django.db.models.Q
        """
        return Q(**{six.text_type(self): value})


class NodeProcessor(object):
    """
    Base class for utilities that work with Django's tree nodes.
    """

    def __init__(self, func):
        """
        Initialize a new node processor.

        :param function func: The function that is applied to nodes and/or
                              their children. The function must take the node
                              item as its first argument as well as potentially
                              more context arguments based on the concrete
                              implementation, which also defines the expected
                              return value.
        """
        self.func = func

    def iter_leaves(self, node):
        """
        Iterate over all leaves of the given node, regardless of the depth of
        potential sub-nodes.

        :param Node node: The node to get the leaves from.
        :return: A generator yielding 3-tuples for each leaf consisting of the
                 (sub-)node the leaf belongs to, the index of the item inside
                 of that leaf and the leaf item itself.
        :rtype: collections.Iterable[Node, int, object]
        """
        for index, child in enumerate(node.children):
            if isinstance(child, Node):
                for result in self.iter_leaves(child):
                    yield result
            else:
                yield node, index, child


class NodeChecker(NodeProcessor):
    """
    A utility to test tree nodes against a condition specified by the
    configured function, which therefore must return a boolean value indicating
    whether or not the condition was met.
    """

    def check_leaves(self, node, **context):
        """
        Check the leaves of the given node object against the configured
        function.

        :param Node node: The node whose leaves should be checked.
        :param context: Additional context parameters that will be passed
                        through to the configured function.
        :return: True if the condition matches at least one leaf; otherwise
                 False.
        :rtype: bool
        """
        for branch_node, index, leaf in self.iter_leaves(node):
            if self.func(leaf, **context):
                return True
        return False


class NodeModifier(NodeProcessor):
    """
    A utility to modify the tree nodes using the configured function, which
    therefore must return the replacement value for a given item.
    """

    def modify_leaves(self, node, copy=True, **context):
        """
        Modify the leaves of the given node object using the configured
        function.

        :param Node node: The node whose leaves should be modified.
        :param bool copy: If True, a copy of the given node will be created and
                          modified, leaving the original node untouched. If
                          False, the original node will be modified in place.
        :param context: Additional context parameters that will be passed
                        through to the configured function.
        :return: The modified node.
        :rtype: Node
        """
        if copy:
            node = deepcopy(node)
        for branch_node, index, leaf in self.iter_leaves(node):
            branch_node.children[index] = self.func(leaf, **context)
        return node


class QueryablePropertyReference(namedtuple('QueryablePropertyReference', 'property model relation_path')):
    """
    A reference to a queryable property that also holds the path to reach the
    property across relations.
    """
    __slots__ = ()
    node_modifier = NodeModifier(lambda item, ref: (six.text_type(ref.relation_path + item[0]), item[1]))

    @property
    def full_path(self):
        """
        Return the full query path to the queryable property (including the
        relation prefix).

        :return: The full path to the queryable property.
        :rtype: QueryPath
        """
        return self.relation_path + self.property.name

    @property
    def descriptor(self):
        """
        Return the descriptor object associated with the queryable property
        this reference points to.

        :return: The queryable property descriptor for the referenced property.
        :rtype: queryable_properties.properties.base.QueryablePropertyDescriptor
        """
        return get_queryable_property_descriptor(self.model, self.property.name)

    def get_filter(self, lookups, value):
        """
        A wrapper for the get_filter method of the property this reference
        points to. It checks if the property actually supports filtering and
        applies the relation path (if any) to the returned Q object.

        :param QueryPath lookups: The lookups/transforms to use for the filter.
        :param value: The value passed to the filter condition.
        :return: A Q object to filter using this property.
        :rtype: django.db.models.Q
        """
        if not self.property.get_filter:
            raise QueryablePropertyError('Queryable property "{}" is supposed to be used as a filter but does not '
                                         'implement filtering.'.format(self.property))

        # Use the model stored on this reference instead of the one on the
        # property since the query may be happening from a subclass of the
        # model the property is defined on.
        q_obj = self.property.get_filter(self.model, six.text_type(lookups) or 'exact', value)
        if self.relation_path:
            # If the resolved property belongs to a related model, all actual
            # conditions in the returned Q object must be modified to use the
            # current relation path as prefix.
            q_obj = self.node_modifier.modify_leaves(q_obj, ref=self)
        return q_obj

    def get_annotation(self):
        """
        A wrapper for the get_annotation method of the property this reference
        points to. It checks if the property actually supports annotation
        creation performs the internal call with the correct model class.

        :return: An annotation object.
        """
        if not self.property.get_annotation:
            raise QueryablePropertyError('Queryable property "{}" needs to be added as annotation but does not '
                                         'implement annotation creation.'.format(self.property))
        # Use the model stored on this reference instead of the one on the
        # property since the query may be happening from a subclass of the
        # model the property is defined on.
        return self.property.get_annotation(self.model)


class InjectableMixin(object):
    """
    A base class for mixin classes that are used to dynamically created classes
    based on a base class and the mixin class.
    """

    # Intentionally use a single cache for all subclasses since it is in no way
    # harmful to use a shared cache.
    _created_classes = {}
    # Class attribute to determine if dynamically built classes should receive
    # a custom __reduce__ implementation so their objects can be pickled.
    _dynamic_pickling = True

    def __init__(self, *args, **kwargs):
        super(InjectableMixin, self).__init__(*args, **kwargs)
        self.init_injected_attrs()

    def init_injected_attrs(self):
        """
        Initialize the attributes this mixin contributes. This method will be
        called during :meth:`__init__` and after the mixin was injected into an
        object.
        """
        pass

    @classmethod
    def mix_with_class(cls, base_class, class_name=None):
        """
        Create a new class based on the given base class and this mixin class.
        If this mixin class is already part of the class hierarchy of the given
        base class, the base class will be returned unchanged.

        :param type base_class: The base class to mix the mixin into.
        :param str class_name: An optional name for the dynamically created
                               class. If None is supplied (default), the class
                               name of the dynamically created class will be
                               the one of the object's original class. Will
                               be applied if a new class is created.
        :return: The generated class or the base class if it already uses this
                 mixin.
        :rtype: type
        """
        if issubclass(base_class, cls):
            return base_class

        class_name = str(class_name or base_class.__name__)
        cache_key = (base_class, cls, class_name)
        created_class = cls._created_classes.get(cache_key)
        if created_class is None:
            attrs = {}
            metaclass = type
            if (not issubclass(cls.__class__, base_class.__class__) and
                    not issubclass(base_class.__class__, cls.__class__)):
                # If the metaclasses of both classes are unrelated, try to build
                # a new metaclass based on both dynamically.
                metaclass = type(base_class.__class__.__name__, (cls.__class__, base_class.__class__), {})
            if cls._dynamic_pickling:
                # Make sure objects of a dynamically created class can be pickled.
                def __reduce__(self):
                    get_state = getattr(self, '__getstate__', lambda: self.__dict__)
                    return _unpickle_injected_object, (base_class, cls, class_name), get_state()
                attrs['__reduce__'] = __reduce__

            created_class = cls._created_classes[cache_key] = metaclass(class_name, (cls, base_class), attrs)
        return created_class

    @classmethod
    def inject_into_object(cls, obj, class_name=None, init=True):
        """
        Update the given object's class by dynamically generating a new class
        based on the object's original class and this mixin class and changing
        the given object into an object of this new class. If this mixin is
        already part of the object's class hierarchy, its class will not
        change.

        :param obj: The object whose class should be changed.
        :param str class_name: An optional name for the dynamically created
                               class. If None is supplied (default), the class
                               name of the dynamically created class will be
                               the one of the object's original class. Will
                               be applied if a new class is created.
        :param bool init: Whether or not to perform the initialization of
                          injected attributes if the object's class was
                          changed.
        :return: The (potentially) modified object.
        """
        new_class = cls.mix_with_class(obj.__class__, class_name)
        if new_class is not obj.__class__:
            obj.__class__ = new_class
            if init:
                obj.init_injected_attrs()
        return obj


# This must be a standalone function for Python 2, where it could not be
# pickled being a static method on the InjectableMixin, even if the underlying
# function had the __safe_for_unpickling__ flag.
def _unpickle_injected_object(base_class, mixin_class, class_name=None):
    """
    Callable for the pickler to unpickle objects of a dynamically created class
    based on the InjectableMixin. It creates the base object from the original
    base class and re-injects the mixin class when unpickling an object.

    :param type base_class: The base class of the pickled object before adding
                            the mixin via injection.
    :param type mixin_class: The :class:`InjectableMixin` subclass that was
                             injected into the pickled object.
    :param str class_name: The class name of the pickled object's dynamically
                           created class.
    :return: The initial unpickled object (before the pickler restores the
             object's state).
    """
    obj = base_class.__new__(base_class, ())
    return mixin_class.inject_into_object(obj, class_name, init=False)


_unpickle_injected_object.__safe_for_unpickling__ = True


class ModelAttributeGetter(object):
    """
    An attribute getter akin to :func:`operator.attrgetter` specifically
    designed for model objects. Like Python's attrgetter, it allows to access
    attributes on related objects using dot-notation, but it catches some
    expected exceptions related to models when following attribute chains.
    It also allows to build filters for querysets based on the configured
    attribute path.
    """

    ATTRIBUTE_SEPARATOR = '.'

    def __init__(self, attribute_path):
        """
        Initialize a new model attribute getter using the specified attribute
        path.

        :param attribute_path: The path to the attribute to retrieve in as
                               an iterable containing the individual parts or
                               a string using dot-notation (see the docs for
                               :func:`operator.attrgetter` for examples). For
                               queryset-related operations, all parts will be
                               combined using the lookup separator (``__``).
        :type attribute_path: collections.Iterable
        """
        if isinstance(attribute_path, six.string_types):
            attribute_path = attribute_path.split(self.ATTRIBUTE_SEPARATOR)
        self.query_path = QueryPath(attribute_path)

    def _get_attribute(self, obj, attribute_name):
        """
        Get and return the value for a single non-nested attribute from the
        given object, catching certain exceptions and returning the
        ``MISSING_OBJECT`` constant in such cases.

        :param obj: The object to get the attribute value from.
        :param str attribute_name: The name of the attribute.
        :return: The attribute value or the ``MISSING_OBJECT`` constant.
        """
        try:
            return getattr(obj, attribute_name)
        except ObjectDoesNotExist:
            # Allow missing DB objects without raising an error, e.g. for
            # reverse one-to-one relations.
            return MISSING_OBJECT
        except AttributeError:
            # Allow objects in between to be None without raising an error,
            # e.g. for nullable fields.
            if obj is None:
                return MISSING_OBJECT
            raise

    def get_value(self, obj):
        """
        Get the value of the attribute configured in this attribute getter from
        the given model object.

        While resolving the attribute on the model object, a few exceptions are
        automatically caught (leading to the ``MISSING_OBJECT`` constant being
        returned):

        * ``AttributeError``, but only if an object in the attribute chain is
          None. This allows to use this getter in conjunction with nullable
          model fields.
        * ``ObjectDoesNotExist``, which is raised by Django e.g. if an object
          does not exist for reverse one-to-one relations. This allows to use
          this getter in conjunction with such relations as well.

        :param django.db.models.Model obj: The model object to retrieve the
                                           value for.
        :return: The value retrieved from the model object.
        """
        for attribute_name in self.query_path:
            obj = self._get_attribute(obj, attribute_name)
            if obj is MISSING_OBJECT:
                break
        return obj

    def get_values(self, obj):
        """
        Similar to :meth:`get_value`, but also handles m2m relations and can
        therefore return multiple values.

        The result is always a list, even if there is only one value. The
        ``MISSING_OBJECT`` constant will never be part of the resulting list
        and simply be omitted instead.

        :param django.db.models.Model obj: The model object to retrieve the
                                           values for.
        :return: A list containing the retrieved values.
        :rtype: list
        """
        values = [obj]
        for attribute_name in self.query_path:
            new_values = []
            for value in values:
                new_value = self._get_attribute(value, attribute_name)
                if isinstance(new_value, Manager):
                    new_values.extend(new_value.all())
                elif new_value is not MISSING_OBJECT:
                    new_values.append(new_value)
            values = new_values
        return values

    def build_filter(self, lookup, value):
        """
        Build a filter condition based on the configured attribute and the
        given lookup and value.

        :param str lookup: The lookup to use for the filter condition.
        :param value: The value to filter against.
        :return: The filter condition as a Q object.
        :rtype: django.db.models.Q
        """
        return (self.query_path + lookup).build_filter(value)


def parametrizable_decorator(function):
    """
    A decorator for functions who themselves are to be used as decorators and
    are to support both a parameter-less decorator usage (``@my_decorator``) as
    well as parametrized decorator usage (``@my_decorator(some_param=5)``).
    This decorator takes care of making the distinction between both usages and
    returning the correct object.

    :param function function: The decorator function to decorate.
    :return: A wrapper function that will replace the decorated function.
    :rtype: function
    """
    @wraps(function)
    def wrapper(decorated_function=None, *args, **kwargs):
        def decorator(func):
            return function(func, *args, **kwargs)

        if decorated_function:  # A function was given directly -> apply the decorator directly (@my_decorator usage).
            return decorator(decorated_function)
        return decorator  # No function -> return the actual decorator (@my_decorator(some_param=5) usage).
    return wrapper


parametrizable_decorator_method = method_decorator(parametrizable_decorator)


def get_queryable_property_descriptor(model, name):
    """
    Retrieve the descriptor object for the property with the given attribute
    name from the given model class or raise an error if no queryable property
    with that name exists on the model class.

    :param type model: The model class to retrieve the descriptor object from.
    :param str name: The name of the property to retrieve the descriptor for.
    :return: The descriptor object.
    :rtype: queryable_properties.properties.base.QueryablePropertyDescriptor
    """
    from ..properties.base import QueryablePropertyDescriptor

    descriptor = getattr(model, name, None)
    if not isinstance(descriptor, QueryablePropertyDescriptor):
        raise QueryablePropertyDoesNotExist("{model} has no queryable property named '{name}'".format(
            model=model.__name__, name=name))
    return descriptor


def resolve_queryable_property(model, query_path):
    """
    Resolve the given path into a queryable property on the given model.

    :param type model: The model to start resolving from.
    :param QueryPath query_path: The query path to resolve.
    :return: A 2-tuple containing a queryable property reference for the
             resolved property and a query path containing the parts of the
             path that represent lookups (or transforms). The first item will
             be None and the query path will be empty if no queryable property
             could be resolved.
    :rtype: (QueryablePropertyReference | None, QueryPath)
    """
    from . import get_queryable_property

    property_ref, lookups = None, QueryPath()
    # Try to follow the given path to allow to use queryable properties
    # across relations.
    for index, name in enumerate(query_path):
        try:
            related_model = get_related_model(model, name)
        except FieldDoesNotExist:
            try:
                prop = get_queryable_property(model, name)
            except QueryablePropertyDoesNotExist:
                # Neither a field nor a queryable property, so likely an
                # invalid name. Do nothing and let Django deal with it.
                pass
            else:
                property_ref = QueryablePropertyReference(prop, model, query_path[:index])
                lookups = query_path[index + 1:]
            # The current name was not a field and either a queryable
            # property or invalid. Either way, resolving ends here.
            break
        else:
            if not related_model:
                # A regular model field that doesn't represent a relation,
                # meaning that no queryable property is involved.
                break
            model = related_model
    return property_ref, lookups


def get_output_field(annotation):
    """
    Return the output field of an annotation if it can be determined.

    :param annotation: The annotation to get the output field from.
    :return: The output field of the annotation or None if it can't be
             determined.
    :rtype: django.db.models.Field | None
    """
    return getattr(annotation, 'output_field', None)
