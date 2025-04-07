# -*- coding: utf-8 -*-
import warnings

import pytest
import six

from queryable_properties.utils import deprecation
from queryable_properties.utils.deprecation import QueryablePropertiesDeprecationWarning, deprecated


class ClassWithDeprecations(object):

    @staticmethod
    @deprecated(hint='This was a staticmethod.')
    def deprecated_staticmethod(*args, **kwargs):
        return kwargs, args

    @classmethod
    @deprecated(hint='This was a classmethod.')
    def deprecated_classmethod(cls, *args, **kwargs):
        return kwargs, args

    @deprecated(hint='This was an instance method.')
    def deprecated_method(self, *args, **kwargs):
        return kwargs, args


@deprecated
def deprecated_function(*args, **kwargs):
    return kwargs, args


@pytest.mark.parametrize('function, current_version, expected_message', [
    (
        deprecated_function,
        (1, 0, 0),
        'deprecated_function (module tests.test_utils.test_deprecation) is deprecated and will be removed in the next '
        'major release (2.0.0).',
    ),
    (
        ClassWithDeprecations().deprecated_method,
        (1, 2, 3),
        '{}deprecated_method (module tests.test_utils.test_deprecation) is deprecated and will be removed in the next '
        'major release (2.0.0). This was an instance method.'.format('ClassWithDeprecations.' if six.PY3 else ''),
    ),
    (
        ClassWithDeprecations.deprecated_classmethod,
        (2, 0, 0),
        '{}deprecated_classmethod (module tests.test_utils.test_deprecation) is deprecated and will be removed in the '
        'next major release (3.0.0). This was a classmethod.'.format('ClassWithDeprecations.' if six.PY3 else ''),
    ),
    (
        ClassWithDeprecations.deprecated_staticmethod,
        (3, 4, 5),
        '{}deprecated_staticmethod (module tests.test_utils.test_deprecation) is deprecated and will be removed in the '
        'next major release (4.0.0). This was a staticmethod.'.format('ClassWithDeprecations.' if six.PY3 else ''),
    ),
])
def test_deprecated(monkeypatch, function, current_version, expected_message):
    monkeypatch.setattr(deprecation, 'VERSION', current_version)
    args, kwargs = (1337, 'test'), dict(key1=42, key2='test')
    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter('always')
        assert function(*args, **kwargs) == (kwargs, args)
        assert len(captured_warnings) == 1
        assert captured_warnings[0].category is QueryablePropertiesDeprecationWarning
        assert six.text_type(captured_warnings[0].message) == expected_message
