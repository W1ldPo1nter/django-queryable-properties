# encoding: utf-8
import pytest

from django.utils.six.moves import cPickle

from queryable_properties.exceptions import QueryablePropertyDoesNotExist
from queryable_properties.properties import QueryableProperty
from queryable_properties.utils import get_queryable_property, InjectableMixin

from .models import VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties


class DummyClass(object):

    def __init__(self, attr1, attr2):
        self.attr1 = attr1
        self.attr2 = attr2


class DummyMixin(InjectableMixin):

    def __init__(self, attr1, attr2, mixin_attr1, mixin_attr2):
        super(DummyMixin, self).__init__(attr1, attr2)
        self.mixin_attr1 = mixin_attr1
        self.mixin_attr2 = mixin_attr2


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
        (VersionWithClassBasedProperties, 'non_existing'),
        (VersionWithDecoratorBasedProperties, 'non_existing'),
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
    def test_create_class(self, monkeypatch, class_name, expected_class_name):
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

    def test_inject_into_object(self):
        obj = DummyClass(5, 'abc')
        DummyMixin.inject_into_object(obj, mixin_attr1=None, mixin_attr2=1.337)
        assert isinstance(obj, DummyClass)
        assert isinstance(obj, DummyMixin)
        assert obj.attr1 == 5
        assert obj.attr2 == 'abc'
        assert obj.mixin_attr1 is None
        assert obj.mixin_attr2 == 1.337

    def test_pickle_unpickle(self):
        base_obj = DummyClass('xyz', 42.42)
        DummyMixin.inject_into_object(base_obj, mixin_attr1='test', mixin_attr2=None)
        serialized_obj = cPickle.dumps(base_obj)
        deserialized_obj = cPickle.loads(serialized_obj)

        for obj in (base_obj, deserialized_obj):
            assert isinstance(obj, DummyClass)
            assert isinstance(obj, DummyMixin)
            assert obj.attr1 == 'xyz'
            assert obj.attr2 == 42.42
            assert obj.mixin_attr1 == 'test'
            assert obj.mixin_attr2 is None
