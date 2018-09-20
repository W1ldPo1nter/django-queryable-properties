# encoding: utf-8
import pytest

from django.utils import six

from queryable_properties import QueryableProperty
from queryable_properties.utils import reset_queryable_property

from .models import (ApplicationWithClassBasedProperty, VersionWithClassBasedProperties,
                     VersionWithDecoratorBasedProperties)


class TestBasics(object):

    @pytest.fixture
    def property_instance(self):
        prop = QueryableProperty()
        prop.name = 'test_prop'
        return prop

    @pytest.fixture
    def model_instance(self):
        instance = ApplicationWithClassBasedProperty(name='Test')
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
    pass


class TestDecorators(object):
    pass
