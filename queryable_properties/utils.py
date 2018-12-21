# encoding: utf-8

from django.utils import six

from .exceptions import QueryablePropertyDoesNotExist


def get_queryable_property(model, name):
    """
    Retrieve the :class:`queryable_properties.properties.QueryableProperty`
    object with the given attribute name from the given model class or raise
    an error if no queryable property with that name exists on the model class.

    :param type model: The model class to retrieve the property object from.
    :param str name: The name of the property to retrieve.
    :return: The queryable property.
    :rtype: queryable_properties.properties.QueryableProperty
    """
    from .properties import QueryableProperty

    prop = getattr(model, name, None)
    if not isinstance(prop, QueryableProperty):
        raise QueryablePropertyDoesNotExist("{model} has no queryable property named '{name}'".format(
            model=model.__name__, name=name))
    return prop


def reset_queryable_property(obj, name):
    """
    Reset the cached value of the queryable property with the given name on the
    given model instance. Read-accessing the property on this model instance at
    a later point will therefore execute the property's getter again.

    :param django.db.models.Model obj: The model instance to reset the cached
                                       value on.
    :param str name: The name of the queryable property.
    """
    prop = get_queryable_property(obj.__class__, name)
    prop._clear_cached_value(obj)


class InjectableMixin(object):
    """
    A base class for mixin classes that are used to dynamically created classes
    based on a base class and the mixin class.
    """

    # Intentionally use a single cache for all subclasses since it is in no way
    # harmful to use a shared cache.
    _created_classes = {}

    @classmethod
    def mix_with_class(cls, base_class, class_name=None):
        """
        Create a new class based on the given base class and this mixin class.

        :param type base_class: The base class to mix the mixin into.
        :param class_name: An optional name for the dynamically created class.
                           If None is supplied (default), the class name of the
                           dynamically created class will be the one of the
                           object's original class.
        :return: The generated class.
        :rtype: type
        """
        class_name = str(class_name or base_class.__name__)
        cache_key = (base_class, cls, class_name)
        created_class = cls._created_classes.get(cache_key)
        if created_class is None:
            created_class = cls._created_classes[cache_key] = type(class_name, (cls, base_class), {})
        return created_class

    @classmethod
    def inject_into_object(cls, obj, class_name=None, **attrs):
        """
        Update the given object's class by dynamically generating a new class
        based on the object's original class and this mixin class and changing
        the given object into an object of this new class.

        :param obj: The object whose class should be changed.
        :param str class_name: An optional name for the dynamically created
                               class. If None is supplied (default), the class
                               name of the dynamically created class will be
                               the one of the object's original class.
        :param attrs: Attributes to set on the given object after its class was
                      changed. This is useful for mixins that add attributes in
                      their initializer, which is not called when changing the
                      class of an object.
        """
        obj.__class__ = cls.mix_with_class(obj.__class__, class_name)
        for name, value in six.iteritems(attrs):
            setattr(obj, name, value)
