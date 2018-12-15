# encoding: utf-8
from mock import Mock
import pytest

from queryable_properties import QueryableProperty
from queryable_properties.exceptions import QueryablePropertyDoesNotExist
from queryable_properties.utils import get_queryable_property, MixinInjector

from .models import VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties


class DummyClass(object):

    def __init__(self, attr1, attr2):
        self.attr1 = attr1
        self.attr2 = attr2


class DummyMixin(object):

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


class TestMixinInjector(object):

    @pytest.fixture
    def injector(self, monkeypatch):
        monkeypatch.setattr(MixinInjector, '_class_cache', {})
        return Mock(wraps=MixinInjector)

    @pytest.mark.parametrize('class_name, expected_class_name', [
        (None, DummyClass.__name__),
        ('TestClass', 'TestClass'),
    ])
    def test_create_class(self, injector, class_name, expected_class_name):
        assert not injector._class_cache.keys()
        created_classes = set()

        # Execute the code twice to test the cache
        for _ in range(2):
            cls = injector.create_class(DummyClass, DummyMixin, class_name)
            created_classes.add(cls)
            assert issubclass(cls, DummyClass)
            assert issubclass(cls, DummyMixin)
            assert cls.__name__ == expected_class_name
            assert len(injector._class_cache.keys()) == 1
            assert len(created_classes) == 1

    def test_inject_into_object(self, injector):
        obj = DummyClass(5, 'abc')
        injector.inject_into_object(obj, DummyMixin, mixin_attr1=None, mixin_attr2=1.337)
        assert isinstance(obj, DummyClass)
        assert isinstance(obj, DummyMixin)
        assert obj.attr1 == 5
        assert obj.attr2 == 'abc'
        assert obj.mixin_attr1 is None
        assert obj.mixin_attr2 == 1.337
