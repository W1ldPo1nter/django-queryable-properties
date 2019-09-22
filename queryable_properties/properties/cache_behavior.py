# encoding: utf-8


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
