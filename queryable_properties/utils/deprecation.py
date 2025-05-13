# -*- coding: utf-8 -*-
import functools
import warnings

from .. import VERSION
from ..compat import compat_getattr
from .internal import parametrizable_decorator


class QueryablePropertiesDeprecationWarning(DeprecationWarning):
    pass


@parametrizable_decorator
def deprecated(function, hint=None):
    """
    Decorator that marks a function or method as deprecated.

    Should be applied *before* other decorators that alter the function's type
    such as ``classmethod`` or ``property``.

    :param function function: The function or method to mark as deprecated.
    :param str | None hint: An optional hint to provide further details
                            regarding the deprecation.
    :return: A wrapper function that will replace the decorated function.
    :rtype: function
    """
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        message = '{} (module {}) is deprecated and will be removed in the next major release ({}.0.0).'.format(
            compat_getattr(function, '__qualname__', '__name__'),
            function.__module__,
            VERSION[0] + 1,
        )
        if hint:
            message = ' '.join((message, hint))
        warnings.warn(message, category=QueryablePropertiesDeprecationWarning, stacklevel=2)
        return function(*args, **kwargs)
    return wrapper
