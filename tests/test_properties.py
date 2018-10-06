# encoding: utf-8
import pytest

from django.db.models import F, Q
from django.utils import six

from queryable_properties import AnnotationMixin, QueryableProperty, queryable_property
from queryable_properties.utils import reset_queryable_property

from .models import (ApplicationWithClassBasedProperties, VersionWithClassBasedProperties,
                     VersionWithDecoratorBasedProperties)


def function_with_docstring():
    """Just a dummy function."""
    pass


class TestBasics(object):

    @pytest.fixture
    def property_instance(self):
        prop = QueryableProperty()
        prop.name = 'test_prop'
        return prop

    @pytest.fixture
    def model_instance(self):
        instance = ApplicationWithClassBasedProperties(name='Test')
        instance.__class__.dummy.counter = 0
        return instance

    def test_contribute_to_class(self, model_instance):
        prop = model_instance.__class__.dummy
        assert isinstance(prop, QueryableProperty)
        assert prop.name == 'dummy'
        assert prop.model is model_instance.__class__
        assert six.get_method_function(model_instance.reset_property) is reset_queryable_property
        # TODO: test that an existing method with the name reset_property will not be overridden

    def test_descriptor_get_class_attribute(self, model_instance):
        assert isinstance(model_instance.__class__.dummy, QueryableProperty)

    @pytest.mark.parametrize('cached, clear_cache, expected_values', [
        (False, False, [1, 2, 3, 4, 5]),  # The implementation of the dummy property returns increasing values ...
        (False, True, [1, 2, 3, 4, 5]),  # ... and cache clears shoudn't matter if caching was disabled all along
        (True, False, [1, 1, 1, 1, 1]),  # Caching is enabled (and never cleared); first value should always be returned
        (True, True, [1, 2, 3, 4, 5]),  # Cache is cleared every time; expect the same result like without caching
    ])
    def test_descriptor_get(self, model_instance, cached, clear_cache, expected_values):
        model_instance.__class__.dummy.cached = cached
        for expected_value in expected_values:
            assert model_instance.dummy == expected_value
            if clear_cache:
                model_instance.reset_property('dummy')

    @pytest.mark.parametrize('cached, clear_cache, values, expected_values', [
        # The setter of the dummy property doesn't actually do anything, so the regular getter values are expected
        # (except for cases with caching, where the cached values are expected)
        (False, False, [0, 0, 0, 0, 0], [1, 2, 3, 4, 5]),
        (False, True, [0, 0, 0, 0, 0], [1, 2, 3, 4, 5]),
        (True, False, [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]),
        (True, True, [0, 0, 0, 0, 0], [1, 2, 3, 4, 5]),
    ])
    def test_descriptor_set(self, model_instance, cached, clear_cache, values, expected_values):
        model_instance.__class__.dummy.cached = cached
        for value, expected_value in zip(values, expected_values):
            model_instance.dummy = value
            if clear_cache:
                model_instance.reset_property('dummy')
            assert model_instance.dummy == expected_value

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_descriptor_set_exception(self, model):
        instance = model()
        with pytest.raises(AttributeError):
            instance.major_minor = '1.3'

    @pytest.mark.parametrize('value', [5, 'test', 1.337, None])
    def test_cache_methods(self, property_instance, model_instance, value):
        # Nothing should be cached initially
        assert not property_instance._has_cached_value(model_instance)
        with pytest.raises(KeyError):
            property_instance._get_cached_value(model_instance)
        # Clear calls should still work even if nothing is cached
        property_instance._clear_cached_value(model_instance)

        # Cache value, then try to use the other methods again
        property_instance._set_cached_value(model_instance, value)
        assert model_instance.__dict__['test_prop'] == value
        assert property_instance._has_cached_value(model_instance)
        assert property_instance._get_cached_value(model_instance) == value

        # Test if clearing the cached value works correctly
        property_instance._clear_cached_value(model_instance)
        assert not property_instance._has_cached_value(model_instance)
        with pytest.raises(KeyError):
            property_instance._get_cached_value(model_instance)


class TestAnnotationMixin(object):

    @pytest.fixture
    def mixin_instance(self):
        instance = AnnotationMixin()
        instance.name = 'test'
        return instance

    @pytest.mark.parametrize('lookup, value', [
        ('exact', 'abc'),
        ('isnull', True),
        ('lte', 5),
    ])
    def test_get_filter(self, mixin_instance, lookup, value):
        q = mixin_instance.get_filter(ApplicationWithClassBasedProperties, lookup, value)
        assert isinstance(q, Q)
        assert len(q.children) == 1
        q_expression, q_value = q.children[0]
        assert q_expression == 'test__{}'.format(lookup)
        assert q_value == value


class TestDecorators(object):

    KWARGS_TO_ATTR_MAP = {  # Maps the queryable_property initializer kwargs to its attributes
        'getter': 'get_value',
        'setter': 'set_value',
        'filter': 'get_filter',
        'annotater': 'get_annotation',
        'updater': 'get_update_kwargs',
        'cached': 'cached',
        'filter_requires_annotation': 'filter_requires_annotation',
        'doc': '__doc__',
    }

    def assert_cloned_property(self, original, clone, changed_attrs):
        assert original is not clone
        for kwarg_name, attr_name in self.KWARGS_TO_ATTR_MAP.items():
            value = getattr(clone, attr_name)
            # Check for a new docstring that was set via a new getter
            if kwarg_name == 'doc' and 'doc' not in changed_attrs and original.__doc__ is None and clone.get_value:
                assert clone.__doc__ == clone.get_value.__doc__
            elif kwarg_name in changed_attrs:
                assert value == changed_attrs[kwarg_name]
            else:
                assert value == getattr(original, attr_name)

    def decorate_function(self, func, decorator, decorator_kwargs=None):
        if decorator_kwargs is not None:
            decorator = decorator(**decorator_kwargs)
        return decorator(func)

    def test_extract_function(self):
        def func():
            pass
        cls_method = classmethod(func)

        prop = queryable_property()
        # Test both regular functions as well as class methods
        assert prop._extract_function(func) is func
        assert prop._extract_function(cls_method) is func

    @pytest.mark.parametrize('init_kwargs, clone_kwargs', [
        ({'getter': lambda: None}, {'setter': lambda: None}),  # Set an additional attribute
        ({'getter': lambda: None}, {'getter': lambda: 'test'}),  # Override an attribute
        ({'getter': lambda: None, 'cached': False}, {'setter': lambda: None, 'cached': True, 'doc': 'my docstring'}),
        ({'getter': lambda: None}, {'getter': function_with_docstring}),  # Set docstring via getter
    ])
    def test_clone(self, init_kwargs, clone_kwargs):
        prop = queryable_property(**init_kwargs)
        clone = prop._clone(**clone_kwargs)
        self.assert_cloned_property(prop, clone, clone_kwargs)

    @pytest.mark.parametrize('docstring, kwargs', [
        (None, None),  # Test @queryable_property
        (None, {}),  # Test @queryable_property() (without any arguments)
        ('my docstring', {}),  # Test if the docstring of the getter is used correctly
        (None, {'doc': 'nice docstring'}),  # Test explicit docstring
        ('my docstring', {'doc': 'nice docstring'}),  # Both docstring options: explicit should take precedence
        (None, {'cached': True, 'filter_requires_annotation': True}),  # Multiple keyword arguments
        (None, {'filter': lambda: Q()})  # Even set other functions
    ])
    def test_initializer(self, docstring, kwargs):
        def func():
            pass
        func.__doc__ = docstring
        prop = self.decorate_function(func, queryable_property, kwargs)
        assert prop.get_value is func
        if kwargs and 'doc' not in kwargs:
            assert prop.__doc__ == docstring
        if kwargs:
            for name, value in kwargs.items():
                assert getattr(prop, self.KWARGS_TO_ATTR_MAP[name]) == value

    @pytest.mark.parametrize('old_value, kwargs', [
        (None, None),
        (lambda: 'test', None),  # Test that the decorated function overrides an existing one
        (None, {'cached': True}),
        (lambda: 'test', {'cached': True}),
    ])
    def test_getter(self, old_value, kwargs):
        original = queryable_property(getter=old_value)

        def func():
            pass

        clone = self.decorate_function(func, original.getter, kwargs)
        self.assert_cloned_property(original, clone, dict(kwargs or {}, getter=func))

    @pytest.mark.parametrize('old_value', [None, lambda: None])
    def test_setter(self, old_value):
        original = queryable_property(setter=old_value)

        def func():
            pass

        clone = self.decorate_function(func, original.setter)
        self.assert_cloned_property(original, clone, {'setter': func})

    @pytest.mark.parametrize('init_kwargs, decorator_kwargs, expected_requires_annotation', [
        ({'filter': lambda: Q()}, {}, None),
        ({'filter': lambda: Q()}, None, None),
        # The following are the 9 cases for initial fra to decorator fra (each can be None, False or True)
        ({}, {}, None),
        ({'filter_requires_annotation': False}, {}, False),
        ({'filter_requires_annotation': True}, {}, True),
        ({}, {'requires_annotation': False}, False),
        ({'filter_requires_annotation': False}, {'requires_annotation': False}, False),
        ({'filter_requires_annotation': True}, {'requires_annotation': False}, False),
        ({}, {'requires_annotation': True}, True),
        ({'filter_requires_annotation': False}, {'requires_annotation': True}, True),
        ({'filter_requires_annotation': True}, {'requires_annotation': True}, True),
    ])
    def test_filter(self, init_kwargs, decorator_kwargs, expected_requires_annotation):
        original = queryable_property(**init_kwargs)

        def func():
            pass

        clone = self.decorate_function(func, original.filter, decorator_kwargs)
        self.assert_cloned_property(original, clone,
                                    {'filter': func, 'filter_requires_annotation': expected_requires_annotation})

    @pytest.mark.parametrize('init_kwargs, should_use_mixin, expected_requires_annotation', [
        ({'annotater': lambda: F('dummy')}, True, True),
        ({}, True, True),
        ({'filter_requires_annotation': False}, True, False),
        ({'filter_requires_annotation': True}, True, True),
        ({'filter': lambda: Q()}, False, True),
        ({'filter': lambda: Q(), 'filter_requires_annotation': False}, False, False),
        ({'filter': lambda: Q(), 'filter_requires_annotation': True}, False, True),
    ])
    def test_annotater(self, init_kwargs, should_use_mixin, expected_requires_annotation):
        original = queryable_property(**init_kwargs)

        def func():
            pass

        clone = self.decorate_function(func, original.annotater)
        changed_attrs = {'annotater': func, 'filter_requires_annotation': expected_requires_annotation}
        if should_use_mixin:
            changed_attrs['filter'] = clone.get_filter
        self.assert_cloned_property(original, clone, changed_attrs)
        assert isinstance(clone, AnnotationMixin) is should_use_mixin

    @pytest.mark.parametrize('old_value', [None, lambda: {}])
    def test_updater(self, old_value):
        original = queryable_property(updater=old_value)

        def func():
            pass

        clone = self.decorate_function(classmethod(func), original.updater)
        self.assert_cloned_property(original, clone, {'updater': func})
