# encoding: utf-8
import pytest
import six
from django import VERSION as DJANGO_VERSION
from django.db.models import Count, F, Model, Q

from queryable_properties.compat import nullcontext as does_not_raise
from queryable_properties.exceptions import QueryablePropertyError
from queryable_properties.properties import (
    CACHE_RETURN_VALUE, CACHE_VALUE, CLEAR_CACHE, DO_NOTHING, AnnotationGetterMixin, AnnotationMixin, LookupFilterMixin,
    QueryableProperty, queryable_property,
)
from queryable_properties.query import QUERYING_PROPERTIES_MARKER
from queryable_properties.properties.base import QueryablePropertyDescriptor, QueryablePropertyReference
from queryable_properties.utils import get_queryable_property, reset_queryable_property
from queryable_properties.utils.internal import QueryPath
from ..app_management.models import (
    ApplicationWithClassBasedProperties, Category, DummyProperty, VersionWithClassBasedProperties,
    VersionWithDecoratorBasedProperties,
)


def function_with_docstring():
    """Just a dummy function."""
    pass


@pytest.fixture
def dummy_property():
    prop = get_queryable_property(ApplicationWithClassBasedProperties, 'dummy')
    prop.counter = 0
    return prop


@pytest.fixture
def model_instance():
    return ApplicationWithClassBasedProperties(name='Test')


class TestQueryablePropertyDescriptor(object):

    def test_initializer(self):
        prop = QueryableProperty()
        prop.__doc__ = 'Test property'
        descriptor = QueryablePropertyDescriptor(prop)
        assert descriptor.prop is prop
        assert descriptor.__doc__ == prop.__doc__

    def test_get_class_attribute(self, dummy_property):
        descriptor = getattr(dummy_property.model, dummy_property.name)
        assert isinstance(descriptor, QueryablePropertyDescriptor)
        assert descriptor.prop is dummy_property

    @pytest.mark.parametrize('ignore, cached, clear_cache, expected_values', [
        (False, False, False, [1, 2, 3, 4, 5]),  # The implementation of the dummy property returns increasing values
        (False, True, False, [1, 1, 1, 1, 1]),  # Values are cached and never cleared, resulting in the first value
        (False, True, True, [1, 2, 3, 4, 5]),  # Cache is cleared every time; expect the same result as without caching
        (True, True, False, [1, 2, 3, 4, 5]),  # Values are cached and never cleared, but cached values are ignored
    ])
    def test_get(self, monkeypatch, dummy_property, model_instance, ignore, cached, clear_cache, expected_values):
        descriptor = getattr(dummy_property.model, dummy_property.name)
        monkeypatch.setattr(descriptor, '_ignore_cached_value', ignore)
        monkeypatch.setattr(dummy_property, 'cached', cached)
        for expected_value in expected_values:
            assert getattr(model_instance, dummy_property.name) == expected_value
            if clear_cache:
                model_instance.reset_property(dummy_property.name)

    def test_get_exception(self, monkeypatch, dummy_property, model_instance):
        monkeypatch.setattr(dummy_property, 'get_value', None)
        with pytest.raises(AttributeError):
            getattr(model_instance, dummy_property.name)

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
    def test_set(self, monkeypatch, dummy_property, model_instance,
                 cached, setter_cache_behavior, values, expected_values):
        monkeypatch.setattr(dummy_property, 'cached', cached)
        monkeypatch.setattr(dummy_property, 'setter_cache_behavior', setter_cache_behavior)
        for value, expected_value in zip(values, expected_values):
            setattr(model_instance, dummy_property.name, value)
            assert getattr(model_instance, dummy_property.name) == expected_value

    @pytest.mark.parametrize('setter_cache_behavior', [CLEAR_CACHE, CACHE_VALUE, CACHE_RETURN_VALUE, DO_NOTHING])
    def test_set_querying_properties_marker(self, monkeypatch, dummy_property, model_instance, setter_cache_behavior):
        monkeypatch.setattr(dummy_property, 'setter_cache_behavior', setter_cache_behavior)
        setattr(model_instance, QUERYING_PROPERTIES_MARKER, True)
        setattr(model_instance, dummy_property.name, 1337)
        descriptor = getattr(model_instance.__class__, dummy_property.name)
        assert descriptor.has_cached_value(model_instance)
        assert descriptor.get_cached_value(model_instance) == 1337

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_set_via_init_kwargs(self, model):
        """Test that properties with a setter can be set via the corresponding model's init kwargs."""
        instance = model(version='11.22.33', changes='Various Bugfixes')
        assert instance.major == '11'
        assert instance.minor == '22'
        assert instance.patch == '33'

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_set_exception(self, model):
        instance = model()
        with pytest.raises(AttributeError):
            instance.major_minor = '1.3'

    @pytest.mark.parametrize('value', [5, 'test', 1.337, None])
    def test_cache_methods(self, dummy_property, model_instance, value):
        descriptor = getattr(model_instance.__class__, dummy_property.name)
        # Nothing should be cached initially
        assert not descriptor.has_cached_value(model_instance)
        with pytest.raises(KeyError):
            descriptor.get_cached_value(model_instance)
        # Clear calls should still work even if nothing is cached
        descriptor.clear_cached_value(model_instance)

        # Cache value, then try to use the other methods again
        descriptor.set_cached_value(model_instance, value)
        assert model_instance.__dict__[dummy_property.name] == value
        assert descriptor.has_cached_value(model_instance)
        assert descriptor.get_cached_value(model_instance) == value

        # Test if clearing the cached value works correctly
        descriptor.clear_cached_value(model_instance)
        assert not descriptor.has_cached_value(model_instance)
        with pytest.raises(KeyError):
            descriptor.get_cached_value(model_instance)

    def test_representations(self, dummy_property):
        descriptor = getattr(dummy_property.model, dummy_property.name)
        assert six.text_type(descriptor) == six.text_type(dummy_property)
        assert repr(descriptor) == '<QueryablePropertyDescriptor: {}>'.format(six.text_type(descriptor))


class TestQueryableProperty(object):

    @pytest.mark.parametrize('kwargs', [
        {},
        {'verbose_name': 'Test Property'},
    ])
    def test_initializer(self, kwargs):
        prop = QueryableProperty(**kwargs)
        assert prop.name is None
        assert prop.model is None
        assert prop.setter_cache_behavior is CLEAR_CACHE
        assert prop.verbose_name == kwargs.get('verbose_name')

    def test_short_description(self):
        prop = QueryableProperty(verbose_name='Test Property')
        assert prop.short_description == 'Test Property'

    def test_contribute_to_class(self, dummy_property, model_instance):
        descriptor = getattr(model_instance.__class__, dummy_property.name)
        assert isinstance(descriptor, QueryablePropertyDescriptor)
        assert descriptor.prop is dummy_property
        assert isinstance(dummy_property, QueryableProperty)
        assert dummy_property.name == 'dummy'
        assert dummy_property.verbose_name == 'Dummy'
        assert dummy_property.model is model_instance.__class__
        assert six.get_method_function(model_instance.reset_property) is reset_queryable_property
        # TODO: test that an existing method with the name reset_property will not be overridden

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_pickle_unpickle(self, model):
        prop = get_queryable_property(model, 'version')
        serialized_prop = six.moves.cPickle.dumps(prop)
        deserialized_prop = six.moves.cPickle.loads(serialized_prop)
        assert deserialized_prop is prop

    @pytest.mark.parametrize('prop, expected_str, expected_class_name', [
        (get_queryable_property(ApplicationWithClassBasedProperties, 'dummy'),
         'tests.app_management.models.ApplicationWithClassBasedProperties.dummy', 'DummyProperty'),
        (get_queryable_property(VersionWithClassBasedProperties, 'is_beta'),
         'tests.dummy_lib.models.ReleaseTypeModel.is_beta', 'ValueCheckProperty'),
    ])
    def test_representations(self, prop, expected_str, expected_class_name):
        assert six.text_type(prop) == expected_str
        assert repr(prop) == '<{}: {}>'.format(expected_class_name, expected_str)

    def test_invalid_property_name(self):
        with pytest.raises(QueryablePropertyError, match='must not contain the lookup separator'):
            type('Broken', (Model,), {'dummy__dummy': DummyProperty(), '__module__': 'tests.app_management.models'})

    @pytest.mark.parametrize('model, relation_path', [
        (None, QueryPath()),
        (VersionWithClassBasedProperties, QueryPath('application')),
    ])
    def test_get_ref(self, dummy_property, model, relation_path):
        ref = dummy_property._get_ref(model, relation_path)
        assert isinstance(ref, QueryablePropertyReference)
        assert ref.property is dummy_property
        assert ref.model is (model or dummy_property.model)
        assert ref.relation_path == relation_path


class TestDecorators(object):

    ATTR_NAMES = ('get_value', 'set_value', 'get_filter', 'get_annotation', 'get_update_kwargs', 'cached',
                  'setter_cache_behavior', 'filter_requires_annotation', 'lookup_mappings', '__doc__')

    def assert_cloned_property(self, original, clone, changed_attrs):
        assert original is not clone
        for attr_name in self.ATTR_NAMES:
            value = getattr(clone, attr_name, None)
            assert value == changed_attrs.get(attr_name, getattr(original, attr_name, None))

    def decorate_function(self, func, decorator, decorator_kwargs=None):
        if decorator_kwargs is not None:
            decorator = decorator(**decorator_kwargs)
        return decorator(func)

    def test_extract_function(self):
        def func():
            pass
        cls_method = classmethod(func)

        prop = queryable_property()
        # Test both regular functions and class methods
        assert prop._extract_function(func) is func
        assert prop._extract_function(cls_method) is func

    @pytest.mark.parametrize('init_kwargs, clone_kwargs', [
        ({'getter': lambda: None}, {'set_value': lambda: None}),  # Set an additional attribute
        ({'getter': lambda: None}, {'get_value': lambda: 'test'}),  # Override an attribute
        ({'getter': lambda: None, 'cached': False},
         {'set_value': lambda: None, 'cached': True, '__doc__': 'my docstring'}),
    ])
    def test_clone(self, init_kwargs, clone_kwargs):
        prop = queryable_property(**init_kwargs)
        clone = prop._clone(**clone_kwargs)
        self.assert_cloned_property(prop, clone, clone_kwargs)

    @pytest.mark.parametrize('docstring, kwargs', [
        (None, None),  # Test @queryable_property
        (None, {}),  # Test @queryable_property() (without any arguments)
        ('my docstring', {}),  # Test if the docstring of the getter is used correctly
        (None, {'cached': True}),
        (None, {'annotation_based': True}),
        ('my docstring', {'annotation_based': True, 'cached': True}),
    ])
    def test_initializer(self, docstring, kwargs):
        def func():
            pass
        func.__doc__ = docstring
        prop = self.decorate_function(func, queryable_property, kwargs)
        assert prop.__doc__ == (docstring or None)
        kwargs = kwargs or {}
        assert prop.cached is (kwargs.get('cached') or False)
        annotation_based = kwargs.get('annotation_based', False)
        assert isinstance(prop, AnnotationGetterMixin) is annotation_based
        if annotation_based:
            assert prop.get_value == six.create_bound_method(six.get_unbound_function(AnnotationGetterMixin.get_value),
                                                             prop)
            assert prop.get_annotation is func
        else:
            assert prop.get_value is func
            assert prop.get_annotation is None

    @pytest.mark.parametrize('old_getter, init_kwargs, old_docstring, new_docstring, kwargs', [
        (None, {}, None, None, None),
        (lambda: 'test', {}, 'my old func', None, None),  # Test that the decorated function overrides an existing one
        (None, {}, None, 'my new func', {'cached': True}),
        (lambda: 'test', {}, 'my old func', 'my new func', {'cached': True}),
        (None, {'annotation_based': True}, None, 'my new func', None),
        (lambda: 'test', {'annotation_based': True}, 'my old func', 'my new func', {'cached': True}),
    ])
    def test_getter(self, old_getter, init_kwargs, old_docstring, new_docstring, kwargs):
        original = queryable_property(old_getter, **init_kwargs)
        if old_docstring is not None:
            original.__doc__ = old_docstring

        def func():
            pass
        func.__doc__ = new_docstring

        clone = self.decorate_function(func, original.getter, kwargs)
        changed_attrs = dict(kwargs or {}, get_value=func, __doc__=new_docstring or old_docstring)
        if init_kwargs.get('annotation_based', False):
            changed_attrs['get_filter'] = six.create_bound_method(
                six.get_unbound_function(AnnotationMixin.get_filter), clone)
            changed_attrs['get_annotation'] = six.create_bound_method(
                six.get_unbound_function(AnnotationMixin.get_annotation), clone)
        self.assert_cloned_property(original, clone, changed_attrs)

    @pytest.mark.parametrize('old_setter, kwargs', [
        (None, None),
        (lambda: None, None),
        (None, {'setter_cache_behavior': DO_NOTHING}),
        (lambda: None, {'setter_cache_behavior': CACHE_VALUE}),
    ])
    def test_setter(self, old_setter, kwargs):
        original = queryable_property()
        original.set_value = old_setter

        def func():
            pass

        decorator_kwargs = kwargs and dict(kwargs)
        if decorator_kwargs:
            decorator_kwargs['cache_behavior'] = decorator_kwargs.pop('setter_cache_behavior')
        clone = self.decorate_function(func, original.setter, decorator_kwargs)
        self.assert_cloned_property(original, clone, dict(kwargs or {}, set_value=func))

    @pytest.mark.parametrize('initial_values, decorator_kwargs, expected_requires_annotation', [
        ({'get_filter': lambda: Q()}, {}, False),
        ({'get_filter': lambda: Q()}, None, False),
        # The following are the 9 cases for initial fra to decorator fra (each can be None, False or True)
        ({}, {}, False),
        ({'filter_requires_annotation': False}, {}, False),
        ({'filter_requires_annotation': True}, {}, True),
        ({}, {'requires_annotation': False}, False),
        ({'filter_requires_annotation': False}, {'requires_annotation': False}, False),
        ({'filter_requires_annotation': True}, {'requires_annotation': False}, False),
        ({}, {'requires_annotation': True}, True),
        ({'filter_requires_annotation': False}, {'requires_annotation': True}, True),
        ({'filter_requires_annotation': True}, {'requires_annotation': True}, True),
    ])
    def test_filter(self, initial_values, decorator_kwargs, expected_requires_annotation):
        original = queryable_property()
        original.__dict__.update(initial_values)

        def func():
            pass

        clone = self.decorate_function(func, original.filter, decorator_kwargs)
        assert not isinstance(clone, LookupFilterMixin)
        self.assert_cloned_property(original, clone,
                                    {'get_filter': func, 'filter_requires_annotation': expected_requires_annotation})

    def test_lookup_filters(self):
        original = queryable_property()
        original.model = Category
        original.name = 'test_property'
        get_filter_func = six.get_unbound_function(LookupFilterMixin.get_filter)

        def func1(cls, lookup, value):
            return 1

        clone1 = self.decorate_function(func1, original.filter, {'lookups': ['lt', 'gt']})
        assert isinstance(clone1, LookupFilterMixin)
        self.assert_cloned_property(original, clone1, {
            'lookup_mappings': {'lt': func1, 'gt': func1},
            'get_filter': six.create_bound_method(get_filter_func, clone1),
        })
        assert clone1.get_filter(None, 'lt', None) == 1
        assert clone1.get_filter(None, 'gt', None) == 1
        with pytest.raises(QueryablePropertyError):
            clone1.get_filter(None, 'in', None)

        def func2(cls, lookup, value):
            return 2

        clone2 = self.decorate_function(func2, clone1.filter, {
            'lookups': ['lt', 'lte'],
            'requires_annotation': True,
            'remaining_lookups_via_parent': True,
        })
        assert isinstance(clone2, LookupFilterMixin)
        self.assert_cloned_property(clone1, clone2, {
            'lookup_mappings': {'lt': func2, 'lte': func2, 'gt': func1},
            'get_filter': six.create_bound_method(get_filter_func, clone2),
            'filter_requires_annotation': True,  # Should be overridable on every call.
            'remaining_lookups_via_parent': True,  # Should be overridable on every call.
        })
        assert clone2.get_filter(None, 'lt', None) == 2
        assert clone2.get_filter(None, 'lte', None) == 2
        assert clone2.get_filter(None, 'gt', None) == 1
        with pytest.raises(TypeError):  # super().get_filter will be None, which isn't callable
            clone2.get_filter(None, 'in', None)

        def func3(cls, lookup, value):
            return 3

        clone3 = self.decorate_function(func3, clone2.filter, {
            'lookups': ['exact'],
            'requires_annotation': False,
            'remaining_lookups_via_parent': False,
        })
        assert isinstance(clone3, LookupFilterMixin)
        self.assert_cloned_property(clone2, clone3, {
            'lookup_mappings': {'lt': func2, 'lte': func2, 'gt': func1, 'exact': func3},
            'get_filter': six.create_bound_method(get_filter_func, clone3),
            'filter_requires_annotation': False,  # Should be overridable on every call.
            'remaining_lookups_via_parent': False,  # Should be overridable on every call.
        })
        assert clone3.get_filter(None, 'lt', None) == 2
        assert clone3.get_filter(None, 'lte', None) == 2
        assert clone3.get_filter(None, 'gt', None) == 1
        assert clone3.get_filter(None, 'exact', None) == 3
        with pytest.raises(QueryablePropertyError):
            clone3.get_filter(None, 'in', None)

    def test_boolean_filter(self):
        original = queryable_property()
        original.model = Category
        original.name = 'test_property'

        def func(cls):
            return Q(some_field=5)

        clone = self.decorate_function(func, original.filter, {'boolean': True})
        assert isinstance(clone, LookupFilterMixin)
        positive_condition = clone.get_filter(None, 'exact', True)
        negative_condition = clone.get_filter(None, 'exact', False)
        if DJANGO_VERSION < (1, 6):
            # In very old Django versions, negating adds another layer.
            negative_condition = negative_condition.children[0]
        assert positive_condition.children == negative_condition.children == [('some_field', 5)]
        assert positive_condition.negated is False
        assert negative_condition.negated is True
        with pytest.raises(QueryablePropertyError):
            clone.get_filter(None, 'lt', None)

    def test_lookup_boolean_exception(self):
        prop = queryable_property()

        def func():
            pass

        with pytest.raises(QueryablePropertyError):
            self.decorate_function(func, prop.filter, {'lookups': ['lt', 'lte'], 'boolean': True})

    @pytest.mark.parametrize('value, lookups, has_mappings, expectation', [
        (None, None, False, does_not_raise()),
        (False, None, False, pytest.raises(QueryablePropertyError)),
        (False, ['lt', 'lte'], False, does_not_raise()),
        (False, None, True, does_not_raise()),
        (True, None, False, pytest.raises(QueryablePropertyError)),
        (True, ['lt', 'lte'], False, does_not_raise()),
        (True, None, True, does_not_raise()),
    ])
    def test_remaining_lookups_via_parent_exception(self, value, lookups, has_mappings, expectation):
        prop = queryable_property()
        if has_mappings:
            prop.lookup_mappings = {}

        def func():
            pass

        with expectation:
            self.decorate_function(func, prop.filter, {'lookups': lookups, 'remaining_lookups_via_parent': value})

    @pytest.mark.parametrize('initial_values, expected_requires_annotation', [
        ({'get_annotation': lambda: F('dummy')}, True),
        ({}, True),
        ({'filter_requires_annotation': False}, False),
        ({'filter_requires_annotation': True}, True),
        ({'get_filter': lambda: Q()}, True),
        ({'get_filter': lambda: Q(), 'filter_requires_annotation': False}, False),
        ({'get_filter': lambda: Q(), 'filter_requires_annotation': True}, True),
    ])
    def test_annotater(self, initial_values, expected_requires_annotation):
        original = queryable_property()
        original.__dict__.update(initial_values)

        def func():
            pass

        prop = self.decorate_function(func, original.annotater)
        assert isinstance(prop, AnnotationMixin)
        self.assert_cloned_property(original, prop, {
            'get_annotation': func,
            'filter_requires_annotation': expected_requires_annotation,
            'get_filter': initial_values.get(
                'get_filter', six.create_bound_method(six.get_unbound_function(AnnotationMixin.get_filter), prop)),
        })

    @pytest.mark.parametrize('old_updater', [None, lambda: {}])
    def test_updater(self, old_updater):
        original = queryable_property()
        original.get_update_kwargs = old_updater

        def func():
            pass

        clone = self.decorate_function(classmethod(func), original.updater)
        self.assert_cloned_property(original, clone, {'get_update_kwargs': func})


class TestQueryablePropertyReference(object):

    @pytest.mark.parametrize('relation_path, expected_result', [
        (QueryPath(), QueryPath('dummy')),
        (QueryPath('application'), QueryPath('application__dummy')),
    ])
    def test_full_path(self, relation_path, expected_result):
        prop = get_queryable_property(ApplicationWithClassBasedProperties, 'dummy')
        ref = QueryablePropertyReference(prop, prop.model, relation_path)
        assert ref.full_path == expected_result

    def test_descriptor(self):
        prop = get_queryable_property(ApplicationWithClassBasedProperties, 'dummy')
        ref = QueryablePropertyReference(prop, prop.model, QueryPath())
        assert ref.descriptor == ApplicationWithClassBasedProperties.dummy

    @pytest.mark.parametrize('lookups, relation_path, expected_filter', [
        (QueryPath(), QueryPath(), 'version_count__exact'),
        (QueryPath('lt'), QueryPath(), 'version_count__lt'),
        (QueryPath('date__year'), QueryPath('application'), 'application__version_count__date__year'),
    ])
    def test_get_filter(self, lookups, relation_path, expected_filter):
        prop = get_queryable_property(ApplicationWithClassBasedProperties, 'version_count')
        ref = QueryablePropertyReference(prop, prop.model, relation_path)
        q = ref.get_filter(lookups, 1337)
        assert isinstance(q, Q)
        assert q.children == [(expected_filter, 1337)]

    def test_get_filter_exception(self):
        prop = get_queryable_property(ApplicationWithClassBasedProperties, 'dummy')
        ref = QueryablePropertyReference(prop, prop.model, QueryPath())
        with pytest.raises(QueryablePropertyError):
            ref.get_filter(QueryPath(), None)

    def test_get_annotation(self):
        prop = get_queryable_property(ApplicationWithClassBasedProperties, 'version_count')
        ref = QueryablePropertyReference(prop, prop.model, QueryPath())
        assert isinstance(ref.get_annotation(), Count)

    def test_get_annotation_exception(self):
        prop = get_queryable_property(ApplicationWithClassBasedProperties, 'dummy')
        ref = QueryablePropertyReference(prop, prop.model, QueryPath())
        with pytest.raises(QueryablePropertyError):
            ref.get_annotation()
