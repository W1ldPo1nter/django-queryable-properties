# encoding: utf-8
import pytest

from queryable_properties import QueryableProperty
from queryable_properties.exceptions import QueryablePropertyDoesNotExist
from queryable_properties.utils import get_queryable_property, inject_mixin

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


@pytest.mark.parametrize('class_name, expected_class_name', [
    (None, DummyClass.__name__),
    ('TestClass', 'TestClass'),
])
def test_inject_mixin(class_name, expected_class_name):
    obj = DummyClass(5, 'abc')
    inject_mixin(obj, DummyMixin, class_name, mixin_attr1=None, mixin_attr2=1.337)
    assert isinstance(obj, DummyClass)
    assert isinstance(obj, DummyMixin)
    assert obj.__class__.__name__ == expected_class_name
    assert obj.attr1 == 5
    assert obj.attr2 == 'abc'
    assert obj.mixin_attr1 is None
    assert obj.mixin_attr2 == 1.337
