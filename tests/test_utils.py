# encoding: utf-8
import pytest

from django.db.models import Q
from six.moves import cPickle

from queryable_properties.exceptions import QueryablePropertyDoesNotExist
from queryable_properties.properties import QueryableProperty
from queryable_properties.utils import (get_queryable_property, InjectableMixin, parametrizable_decorator,
                                        TreeNodeProcessor)

from .models import VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties


class DummyClass(object):

    def __init__(self, attr1, attr2):
        self.attr1 = attr1
        self.attr2 = attr2

    @parametrizable_decorator
    def decorator(self, function, *args, **kwargs):
        function.args = args
        function.kwargs = kwargs
        return function


class DummyMixin(InjectableMixin):

    def init_injected_attrs(self):
        self.mixin_attr1 = 1.337
        self.mixin_attr2 = 'test'


class TestGetQueryableProperty(object):

    @pytest.mark.parametrize('model, property_name', [
        (VersionWithClassBasedProperties, 'major_minor'),
        (VersionWithDecoratorBasedProperties, 'major_minor'),
        (VersionWithClassBasedProperties, 'version'),
        (VersionWithDecoratorBasedProperties, 'version'),
    ])
    def test_property_found(self, model, property_name):
        prop = get_queryable_property(model, property_name)
        assert isinstance(prop, QueryableProperty)

    @pytest.mark.parametrize('model, property_name', [
        (VersionWithClassBasedProperties, 'non_existent'),
        (VersionWithDecoratorBasedProperties, 'non_existent'),
        (VersionWithClassBasedProperties, 'major'),  # Existing model field
        (VersionWithDecoratorBasedProperties, 'major'),  # Existing model field
    ])
    def test_exception(self, model, property_name):
        with pytest.raises(QueryablePropertyDoesNotExist):
            get_queryable_property(model, property_name)


class TestInjectableMixin(object):

    @pytest.mark.parametrize('class_name, expected_class_name', [
        (None, DummyClass.__name__),
        ('TestClass', 'TestClass'),
    ])
    def test_mix_with_class(self, monkeypatch, class_name, expected_class_name):
        monkeypatch.setattr(DummyMixin, '_created_classes', {})
        assert not DummyMixin._created_classes
        created_classes = set()

        # Execute the code twice to test the cache
        for _ in range(2):
            cls = DummyMixin.mix_with_class(DummyClass, class_name)
            created_classes.add(cls)
            assert issubclass(cls, DummyClass)
            assert issubclass(cls, DummyMixin)
            assert cls.__name__ == expected_class_name
            assert len(DummyMixin._created_classes) == 1
            assert len(created_classes) == 1
            # Test that the __init__ method of the new class correctly
            # initializes the injected attributes.
            obj = cls(5, 'abc')
            assert obj.mixin_attr1 == 1.337
            assert obj.mixin_attr2 == 'test'

    def test_inject_into_object(self):
        obj = DummyClass(5, 'abc')
        DummyMixin.inject_into_object(obj)
        assert isinstance(obj, DummyClass)
        assert isinstance(obj, DummyMixin)
        assert obj.attr1 == 5
        assert obj.attr2 == 'abc'
        assert obj.mixin_attr1 == 1.337
        assert obj.mixin_attr2 == 'test'

    def test_pickle_unpickle(self):
        base_obj = DummyClass('xyz', 42.42)
        DummyMixin.inject_into_object(base_obj)
        serialized_obj = cPickle.dumps(base_obj)
        deserialized_obj = cPickle.loads(serialized_obj)

        for obj in (base_obj, deserialized_obj):
            assert isinstance(obj, DummyClass)
            assert isinstance(obj, DummyMixin)
            assert obj.attr1 == 'xyz'
            assert obj.attr2 == 42.42
            assert obj.mixin_attr1 == 1.337
            assert obj.mixin_attr2 == 'test'

    def test_no_reduce_implementation(self, monkeypatch):
        monkeypatch.setattr(DummyMixin, '_dynamic_pickling', False)
        monkeypatch.setattr(DummyMixin, '_created_classes', {})
        base_obj = DummyClass('xyz', 42.42)
        DummyMixin.inject_into_object(base_obj)
        with pytest.raises(cPickle.PicklingError):
            cPickle.dumps(base_obj)


class TestTreeNodeProcessor(object):

    @pytest.mark.parametrize('node, expected_result', [
        (Q(a=1), True),
        (Q(b=2), False),
        (Q(Q(a=1) | Q(b=2), c=3), True),
        (Q(Q(d=1) | Q(b=2), c=3), False),
    ])
    def test_check_leaves(self, node, expected_result):
        # The predicate checks if a leaf for field 'a' exists
        assert TreeNodeProcessor(node).check_leaves(lambda item: item[0] == 'a') is expected_result

    @pytest.mark.parametrize('copy', [True, False])
    def test_modify_tree_node(self, copy):
        q = Q(Q(a=1) | Q(b=2), c=3)
        result = TreeNodeProcessor(q).modify_leaves(
            lambda item: ('prefix_{}_suffix'.format(item[0]), item[1] + 1), copy=copy)
        assert (result is q) is not copy
        children = list(result.children)
        assert ('prefix_c_suffix', 4) in children
        children.remove(('prefix_c_suffix', 4))
        assert ('prefix_a_suffix', 2) in children[0].children
        assert ('prefix_b_suffix', 3) in children[0].children


def test_parametrizable_decorator():
    dummy = DummyClass(1, 2)

    @dummy.decorator
    def func1():
        pass

    @dummy.decorator(some_kwarg=1, another_kwarg='test')
    def func2():
        pass

    def func3():
        pass

    func3 = dummy.decorator(func3, 1, 2, kwarg='test')

    assert func1.args == ()
    assert func1.kwargs == {}
    assert func2.args == ()
    assert func2.kwargs == dict(some_kwarg=1, another_kwarg='test')
    assert func3.args == (1, 2)
    assert func3.kwargs == dict(kwarg='test')
