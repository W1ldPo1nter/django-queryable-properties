# encoding: utf-8
import pytest

import six
from django.db.models import F, Model, Q

from queryable_properties.exceptions import QueryablePropertyError
from queryable_properties.properties import (AnnotationMixin, CACHE_RETURN_VALUE, CACHE_VALUE, CLEAR_CACHE, DO_NOTHING,
                                             LookupFilterMixin, QueryableProperty, queryable_property)
from queryable_properties.utils import reset_queryable_property

from ..models import (ApplicationWithClassBasedProperties, DummyProperty, VersionWithClassBasedProperties,
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
    def test_descriptor_get(self, monkeypatch, model_instance, cached, clear_cache, expected_values):
        monkeypatch.setattr(model_instance.__class__.dummy, 'cached', cached)
        for expected_value in expected_values:
            assert model_instance.dummy == expected_value
            if clear_cache:
                model_instance.reset_property('dummy')

    def test_descriptor_get_exception(self, monkeypatch, model_instance):
        monkeypatch.setattr(model_instance.__class__.dummy, 'get_value', None)
        with pytest.raises(AttributeError):
            model_instance.dummy

    @pytest.mark.parametrize('cached, setter_cache_behavior, values, expected_values', [
        # The setter cache behavior should not make a difference if a property
        # is not cached
        (False, CLEAR_CACHE, [0, 0, 0, 0, 0], [1, 2, 3, 4, 5]),
        (False, CACHE_VALUE, [0, 0, 0, 0, 0], [1, 2, 3, 4, 5]),
        (False, CACHE_RETURN_VALUE, [0, 0, 0, 0, 0], [1, 2, 3, 4, 5]),
        (False, DO_NOTHING, [0, 0, 0, 0, 0], [1, 2, 3, 4, 5]),
        (True, CLEAR_CACHE, [0, 0, 0, 0, 0], [1, 2, 3, 4, 5]),  # Getter always gets called again due to cache clear
        (True, CACHE_VALUE, [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]),  # The raw value gets should get cached
        (True, CACHE_RETURN_VALUE, [0, 0, 0, 0, 0], [-1, -1, -1, -1, -1]),  # The return value should get cached
        (True, DO_NOTHING, [0, 0, 0, 0, 0], [1, 1, 1, 1, 1]),  # The first getter value should get and stay cached
    ])
    def test_descriptor_set(self, monkeypatch, model_instance, cached, setter_cache_behavior, values, expected_values):
        monkeypatch.setattr(model_instance.__class__.dummy, 'cached', cached)
        monkeypatch.setattr(model_instance.__class__.dummy, 'setter_cache_behavior', setter_cache_behavior)
        for value, expected_value in zip(values, expected_values):
            model_instance.dummy = value
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

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_pickle_unpickle(self, model):
        serialized_prop = six.moves.cPickle.dumps(model.version)
        deserialized_prop = six.moves.cPickle.loads(serialized_prop)
        assert deserialized_prop is model.version

    def test_representations(self):
        string_representation = six.text_type(ApplicationWithClassBasedProperties.dummy)
        object_representation = repr(ApplicationWithClassBasedProperties.dummy)
        assert string_representation == 'tests.ApplicationWithClassBasedProperties.dummy'
        assert object_representation == '<DummyProperty: {}>'.format(string_representation)

    def test_invalid_property_name(self):
        with pytest.raises(QueryablePropertyError, match='must not contain the lookup separator'):
            type('BrokenModel', (Model,), {'dummy__dummy': DummyProperty(), '__module__': 'tests.models'})


class TestDecorators(object):

    KWARGS_TO_ATTR_MAP = {  # Maps the queryable_property initializer kwargs to its attributes
        'getter': 'get_value',
        'setter': 'set_value',
        'filter': 'get_filter',
        'annotater': 'get_annotation',
        'updater': 'get_update_kwargs',
        'cached': 'cached',
        'setter_cache_behavior': 'setter_cache_behavior',
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
            else:
                assert value == changed_attrs.get(kwarg_name, getattr(original, attr_name))

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

    @pytest.mark.parametrize('old_value, kwargs', [
        (None, None),
        (lambda: None, None),
        (None, {'setter_cache_behavior': DO_NOTHING}),
        (lambda: None, {'setter_cache_behavior': CACHE_VALUE}),
    ])
    def test_setter(self, old_value, kwargs):
        original = queryable_property(setter=old_value)

        def func():
            pass

        decorator_kwargs = kwargs and dict(kwargs)
        if decorator_kwargs:
            decorator_kwargs['cache_behavior'] = decorator_kwargs.pop('setter_cache_behavior')
        clone = self.decorate_function(func, original.setter, decorator_kwargs)
        self.assert_cloned_property(original, clone, dict(kwargs or {}, setter=func))

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
        assert not isinstance(clone, LookupFilterMixin)
        self.assert_cloned_property(original, clone,
                                    {'filter': func, 'filter_requires_annotation': expected_requires_annotation})

    def test_lookup_filters(self):
        original = queryable_property()
        get_filter_func = six.get_unbound_function(LookupFilterMixin.get_filter)

        def func1(cls, lookup, value):
            return 1

        clone1 = self.decorate_function(func1, original.filter, {'lookups': ['lt', 'gt']})
        assert isinstance(clone1, LookupFilterMixin)
        self.assert_cloned_property(original, clone1, {
            'lookup_mappings': {'lt': func1, 'gt': func1},
            'filter': six.create_bound_method(get_filter_func, clone1),
        })
        assert clone1.get_filter(None, 'lt', None) == 1
        assert clone1.get_filter(None, 'gt', None) == 1

        def func2(cls, lookup, value):
            return 2

        clone2 = self.decorate_function(func2, clone1.filter, {'lookups': ['lt', 'lte'], 'requires_annotation': True})
        assert isinstance(clone2, LookupFilterMixin)
        self.assert_cloned_property(clone1, clone2, {
            'lookup_mappings': {'lt': func2, 'lte': func2, 'gt': func1},
            'filter': six.create_bound_method(get_filter_func, clone2),
            'filter_requires_annotation': True,  # Should be overridable on every call.
        })
        assert clone2.get_filter(None, 'lt', None) == 2
        assert clone2.get_filter(None, 'lte', None) == 2
        assert clone2.get_filter(None, 'gt', None) == 1

        def func3(cls, lookup, value):
            return 3

        clone3 = self.decorate_function(func3, clone2.filter, {'lookups': ['exact'], 'requires_annotation': False})
        assert isinstance(clone3, LookupFilterMixin)
        self.assert_cloned_property(clone2, clone3, {
            'lookup_mappings': {'lt': func2, 'lte': func2, 'gt': func1, 'exact': func3},
            'filter': six.create_bound_method(get_filter_func, clone3),
            'filter_requires_annotation': False,  # Should be overridable on every call.
        })
        assert clone3.get_filter(None, 'lt', None) == 2
        assert clone3.get_filter(None, 'lte', None) == 2
        assert clone3.get_filter(None, 'gt', None) == 1
        assert clone3.get_filter(None, 'exact', None) == 3

    def test_lookup_boolean_exception(self):
        prop = queryable_property()

        def func():
            pass

        with pytest.raises(ValueError):
            self.decorate_function(func, prop.filter, {'lookups': ['lt', 'lte'], 'boolean': True})

    @pytest.mark.parametrize('init_kwargs, expected_requires_annotation', [
        ({'annotater': lambda: F('dummy')}, True),
        ({}, True),
        ({'filter_requires_annotation': False}, False),
        ({'filter_requires_annotation': True}, True),
        ({'filter': lambda: Q()}, True),
        ({'filter': lambda: Q(), 'filter_requires_annotation': False}, False),
        ({'filter': lambda: Q(), 'filter_requires_annotation': True}, True),
    ])
    def test_annotater(self, init_kwargs, expected_requires_annotation):
        original = queryable_property(**init_kwargs)

        def func():
            pass

        prop = self.decorate_function(func, original.annotater)
        assert isinstance(prop, AnnotationMixin)
        self.assert_cloned_property(original, prop, {
            'annotater': func,
            'filter_requires_annotation': expected_requires_annotation,
            'filter': init_kwargs.get(
                'filter', six.create_bound_method(six.get_unbound_function(AnnotationMixin.get_filter), prop)),
        })

    @pytest.mark.parametrize('old_value', [None, lambda: {}])
    def test_updater(self, old_value):
        original = queryable_property(updater=old_value)

        def func():
            pass

        clone = self.decorate_function(classmethod(func), original.updater)
        self.assert_cloned_property(original, clone, {'updater': func})
