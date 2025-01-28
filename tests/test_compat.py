# -*- coding: utf-8 -*-
import sys

import pytest

from queryable_properties.compat import compat_call, compat_getattr, compat_setattr, get_arg_names


class Dummy(object):

    def __init__(self):
        self.attr_a = 1337
        self.attr_b = 'test'

    def method_a(self, arg=1):
        return self.attr_a + arg

    def method_b(self, arg=1):
        return self.attr_b + str(arg)


def test_compat_getattr():
    obj = Dummy()
    with pytest.raises(AttributeError):
        compat_getattr(obj)

    assert compat_getattr(obj, 'attr_a') == 1337
    assert compat_getattr(obj, 'attr_b') == 'test'
    assert compat_getattr(obj, 'attr_a.real') == 1337
    assert compat_getattr(obj, 'attr_a', 'attr_b') == 1337

    del obj.attr_a
    assert compat_getattr(obj, 'attr_a', 'attr_b') == 'test'
    assert compat_getattr(obj, 'attr_a.real', 'attr_b') == 'test'

    del obj.attr_b
    with pytest.raises(AttributeError):
        compat_getattr(obj, 'attr_a', 'attr_b')


def test_compat_setattr():
    obj = Dummy()
    with pytest.raises(AttributeError):
        compat_setattr(obj, 42)

    compat_setattr(obj, 1, 'attr_a')
    assert obj.attr_a == 1
    assert obj.attr_b == 'test'
    compat_setattr(obj, 2, 'attr_a', 'attr_b')
    assert obj.attr_a == 2
    assert obj.attr_b == 'test'

    del obj.attr_a
    with pytest.raises(AttributeError):
        compat_setattr(obj, 3, 'attr_a')
    compat_setattr(obj, 4, 'attr_a', 'attr_b')
    assert obj.attr_b == 4

    del obj.attr_b
    with pytest.raises(AttributeError):
        compat_setattr(obj, 5, 'attr_a', 'attr_b')


def test_compat_call():
    obj = Dummy()
    with pytest.raises(AttributeError):
        compat_call(obj, ())

    assert compat_call(obj, ('method_a',)) == 1338
    assert compat_call(obj, ('method_a',), 2) == 1339
    assert compat_call(obj, ('method_a',), arg=3) == 1340
    assert compat_call(obj, ('attr_b.upper',)) == 'TEST'
    assert compat_call(obj, ('method_a', 'method_b')) == 1338
    assert compat_call(obj, ('method_a', 'method_b'), 2) == 1339
    assert compat_call(obj, ('method_a', 'method_b'), arg=3) == 1340
    assert compat_call(obj, ('attr_b.upper', 'method_b')) == 'TEST'

    with pytest.raises(AttributeError):
        compat_call(obj, ('method_c',))
    assert compat_call(obj, ('method_c', 'method_b')) == 'test1'
    assert compat_call(obj, ('method_c', 'method_b'), 2) == 'test2'
    assert compat_call(obj, ('method_c', 'method_b'), arg=3) == 'test3'

    with pytest.raises(AttributeError):
        compat_call(obj, ('method_c', 'method_d'))


class TestGetArgNames(object):

    @pytest.mark.parametrize('func, expected_result', [
        (lambda: None, []),
        (lambda a, b: None, ['a', 'b']),
        (lambda a=1, b=2: None, ['a', 'b']),
        (lambda a, b=2, *args, **kwargs: None, ['a', 'b']),
    ])
    def test_args_kwargs(self, func, expected_result):
        assert get_arg_names(func) == expected_result

    @pytest.mark.skipif(sys.version_info[0] < 3, reason='Keyword-only arguments only exist in Python 3.')
    def test_keyword_only(self):
        assert get_arg_names(eval('lambda a, *, b=2: None')) == ['a', 'b']
