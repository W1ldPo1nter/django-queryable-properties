# encoding: utf-8
import pytest

from django import VERSION as DJANGO_VERSION
from django.db.models import CharField, IntegerField, Q, Sum
from six.moves import cPickle

from queryable_properties.utils.internal import (
    get_output_field, InjectableMixin, MISSING_OBJECT, ModelAttributeGetter, parametrizable_decorator,
    QueryablePropertyReference, resolve_queryable_property, TreeNodeProcessor
)

from ..app_management.models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                                     CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties,
                                     VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)
from ..conftest import Concat, Value


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


class TestModelAttributeGetter(object):

    @pytest.mark.parametrize('path, expected_parts', [
        ('attr', ['attr']),
        ('attr1.attr2', ['attr1', 'attr2']),
        ('attr1.attr2.attr3', ['attr1', 'attr2', 'attr3']),
    ])
    def test_initializer(self, path, expected_parts):
        getter = ModelAttributeGetter(path)
        assert getter.path_parts == expected_parts

    @pytest.mark.django_db
    @pytest.mark.parametrize('path, expected_value', [
        ('major', 1),
        ('changes', None),
        ('application.name', 'My cool App'),
    ])
    def test_get_value(self, versions, path, expected_value):
        obj = versions[0]
        getter = ModelAttributeGetter(path)
        assert getter.get_value(obj) == expected_value

    @pytest.mark.django_db
    def test_get_value_catch_attribute_error_on_none(self, versions):
        obj = versions[0]
        getter = ModelAttributeGetter('changes.strip')
        assert getter.get_value(obj) is MISSING_OBJECT

    @pytest.mark.django_db
    @pytest.mark.parametrize('path', ['non_existent', 'non.existent', 'application.non_existent'])
    def test_get_value_bubble_attribute_error(self, versions, path):
        obj = versions[0]
        getter = ModelAttributeGetter(path)
        with pytest.raises(AttributeError):
            getter.get_value(obj)

    @pytest.mark.django_db
    def test_get_value_catch_object_does_not_exist(self, applications, versions):
        obj = versions[0].__class__.objects.get(pk=versions[0].pk)  # Refresh from DB
        applications[0].delete()
        getter = ModelAttributeGetter('application.name')
        assert getter.get_value(obj) is MISSING_OBJECT

    @pytest.mark.parametrize('path, lookup, value, expected_query_name', [
        ('attr', 'exact', 1337, 'attr__exact'),
        ('attr1.attr2', 'in', ('test', 'value'), 'attr1__attr2__in'),
        ('attr1.attr2.attr3', 'gt', 1337, 'attr1__attr2__attr3__gt'),
    ])
    def test_build_filter(self, path, lookup, value, expected_query_name):
        getter = ModelAttributeGetter(path)
        condition = getter.build_filter(lookup, value)
        assert isinstance(condition, Q)
        assert condition.children[0] == (expected_query_name, value)


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


class TestResolveQueryableProperty(object):

    @pytest.mark.parametrize('model, path, expected_property, expected_lookups', [
        # No relation involved
        (VersionWithClassBasedProperties, ['version'], VersionWithClassBasedProperties.version, []),
        (VersionWithDecoratorBasedProperties, ['version'], VersionWithDecoratorBasedProperties.version, []),
        (VersionWithClassBasedProperties, ['version', 'lower', 'exact'],
         VersionWithClassBasedProperties.version, ['lower', 'exact']),
        (VersionWithDecoratorBasedProperties, ['version', 'lower', 'exact'],
         VersionWithDecoratorBasedProperties.version, ['lower', 'exact']),
        # FK forward relation
        (VersionWithClassBasedProperties, ['application', 'version_count'],
         ApplicationWithClassBasedProperties.version_count, []),
        (VersionWithDecoratorBasedProperties, ['application', 'version_count'],
         ApplicationWithDecoratorBasedProperties.version_count, []),
        (VersionWithClassBasedProperties, ['application', 'major_sum', 'gt'],
         ApplicationWithClassBasedProperties.major_sum, ['gt']),
        (VersionWithDecoratorBasedProperties, ['application', 'major_sum', 'gt'],
         ApplicationWithDecoratorBasedProperties.major_sum, ['gt']),
        # FK reverse relation
        (ApplicationWithClassBasedProperties, ['versions', 'major_minor'],
         VersionWithClassBasedProperties.major_minor, []),
        (ApplicationWithDecoratorBasedProperties, ['versions', 'major_minor'],
         VersionWithDecoratorBasedProperties.major_minor, []),
        (ApplicationWithClassBasedProperties, ['versions', 'version', 'lower', 'contains'],
         VersionWithClassBasedProperties.version, ['lower', 'contains']),
        (ApplicationWithDecoratorBasedProperties, ['versions', 'version', 'lower', 'contains'],
         VersionWithDecoratorBasedProperties.version, ['lower', 'contains']),
        # M2M forward relation
        (ApplicationWithClassBasedProperties, ['categories', 'circular'],
         CategoryWithClassBasedProperties.circular, []),
        (ApplicationWithDecoratorBasedProperties, ['categories', 'circular'],
         CategoryWithDecoratorBasedProperties.circular, []),
        (ApplicationWithClassBasedProperties, ['categories', 'circular', 'exact'],
         CategoryWithClassBasedProperties.circular, ['exact']),
        (ApplicationWithDecoratorBasedProperties, ['categories', 'circular', 'exact'],
         CategoryWithDecoratorBasedProperties.circular, ['exact']),
        # M2M reverse relation
        (CategoryWithClassBasedProperties, ['applications', 'major_sum'],
         ApplicationWithClassBasedProperties.major_sum, []),
        (CategoryWithDecoratorBasedProperties, ['applications', 'major_sum'],
         ApplicationWithDecoratorBasedProperties.major_sum, []),
        (CategoryWithClassBasedProperties, ['applications', 'version_count', 'lt'],
         ApplicationWithClassBasedProperties.version_count, ['lt']),
        (CategoryWithDecoratorBasedProperties, ['applications', 'version_count', 'lt'],
         ApplicationWithDecoratorBasedProperties.version_count, ['lt']),
        # Multiple relations
        (CategoryWithClassBasedProperties, ['applications', 'versions', 'application', 'categories', 'circular'],
         CategoryWithClassBasedProperties.circular, []),
        (CategoryWithDecoratorBasedProperties, ['applications', 'versions', 'application', 'categories', 'circular'],
         CategoryWithDecoratorBasedProperties.circular, []),
        (VersionWithClassBasedProperties, ['application', 'categories', 'circular', 'in'],
         CategoryWithClassBasedProperties.circular, ['in']),
        (VersionWithDecoratorBasedProperties, ['application', 'categories', 'circular', 'in'],
         CategoryWithDecoratorBasedProperties.circular, ['in']),
    ])
    def test_successful(self, model, path, expected_property, expected_lookups):
        expected_ref = QueryablePropertyReference(expected_property, expected_property.model,
                                                  tuple(path[:-len(expected_lookups) - 1]))
        assert resolve_queryable_property(model, path) == (expected_ref, expected_lookups)

    @pytest.mark.parametrize('model, path', [
        # No relation involved
        (VersionWithClassBasedProperties, ['non_existent']),
        (VersionWithDecoratorBasedProperties, ['non_existent']),
        (VersionWithClassBasedProperties, ['major']),
        (VersionWithDecoratorBasedProperties, ['major']),
        # FK forward relation
        (VersionWithClassBasedProperties, ['application', 'non_existent', 'exact']),
        (VersionWithDecoratorBasedProperties, ['application', 'non_existent', 'exact']),
        (VersionWithClassBasedProperties, ['application', 'name']),
        (VersionWithDecoratorBasedProperties, ['application', 'name']),
        # FK reverse relation
        (ApplicationWithClassBasedProperties, ['versions', 'non_existent']),
        (ApplicationWithDecoratorBasedProperties, ['versions', 'non_existent']),
        (ApplicationWithClassBasedProperties, ['versions', 'minor', 'gt']),
        (ApplicationWithDecoratorBasedProperties, ['versions', 'minor', 'gt']),
        # M2M forward relation
        (ApplicationWithClassBasedProperties, ['categories', 'non_existent']),
        (ApplicationWithDecoratorBasedProperties, ['categories', 'non_existent']),
        (ApplicationWithClassBasedProperties, ['categories', 'name']),
        (ApplicationWithDecoratorBasedProperties, ['categories', 'name']),
        # M2M reverse relation
        (CategoryWithClassBasedProperties, ['applications', 'non_existent']),
        (CategoryWithDecoratorBasedProperties, ['applications', 'non_existent']),
        (CategoryWithClassBasedProperties, ['applications', 'name']),
        (CategoryWithDecoratorBasedProperties, ['applications', 'name']),
        # Non existent relation
        (VersionWithClassBasedProperties, ['non_existent_relation', 'non_existent', 'in']),
        (VersionWithDecoratorBasedProperties, ['non_existent_relation', 'non_existent', 'in']),
    ])
    def test_unsuccessful(self, model, path):
        assert resolve_queryable_property(model, path) == (None, [])


class TestGetOutputField(object):

    CHAR_FIELD = CharField()
    INTEGER_FIELD = IntegerField(null=True)

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Output fields couldn't be declared before Django 1.8")
    @pytest.mark.parametrize('annotation, expected_result', [
        (Concat(Value('test'), 'some_field', output_field=CHAR_FIELD), CHAR_FIELD),
        (Sum('aggregate', output_field=INTEGER_FIELD), INTEGER_FIELD),
    ])
    def test_success(self, annotation, expected_result):
        assert get_output_field(annotation) is expected_result

    @pytest.mark.parametrize('annotation', [Concat(Value('test'), 'some_field'), Sum('aggregate')])
    def test_none(self, annotation):
        assert get_output_field(annotation) is None
