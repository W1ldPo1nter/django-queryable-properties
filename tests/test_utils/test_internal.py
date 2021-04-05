# encoding: utf-8
import pytest

import six
from django import VERSION as DJANGO_VERSION
from django.db.models import CharField, IntegerField, Q, Sum
from six.moves import cPickle

from queryable_properties.utils.internal import (
    get_output_field, InjectableMixin, MISSING_OBJECT, ModelAttributeGetter, parametrizable_decorator,
    QueryablePropertyReference, QueryPath, resolve_queryable_property, TreeNodeProcessor
)

from ..app_management.models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                                     CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties,
                                     VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)
from ..conftest import Concat, Value


class BaseMetaclass(type):
    pass


class MixinMetaclass(type):
    pass


class DummyClass(object):

    def __init__(self, attr1, attr2):
        self.attr1 = attr1
        self.attr2 = attr2


class DummyMixin(InjectableMixin):

    def init_injected_attrs(self):
        self.mixin_attr1 = 1.337
        self.mixin_attr2 = 'test'


class DummyClassWithMetaclass(six.with_metaclass(BaseMetaclass)):
    pass


class DummyMixinWithMetaclass(six.with_metaclass(MixinMetaclass, InjectableMixin)):
    pass


@parametrizable_decorator
def decorator(function, *args, **kwargs):
    function.args = args
    function.kwargs = kwargs
    return function


class TestQueryPath(object):

    @pytest.mark.parametrize('path, expected_result', [
        ([], QueryPath()),
        (('a', 'b'), QueryPath(('a', 'b'))),
        ('a__b', QueryPath(('a', 'b'))),
    ])
    def test_constructor(self, path, expected_result):
        query_path = QueryPath(path)
        assert query_path == expected_result

    @pytest.mark.parametrize('query_path, addition, expected_result', [
        (QueryPath(), QueryPath(['a']), QueryPath(('a',))),
        (QueryPath('a'), ('b', 'c'), QueryPath(('a', 'b', 'c'))),
        (QueryPath('a'), ['b'], QueryPath(('a', 'b'))),
        (QueryPath(('a', 'b')), 'c__d', QueryPath(('a', 'b', 'c', 'd'))),
    ])
    def test_add(self, query_path, addition, expected_result):
        result = query_path + addition
        assert isinstance(result, QueryPath)
        assert result == expected_result

    @pytest.mark.parametrize('query_path, item, expected_result', [
        (QueryPath('a__b'), 0, 'a'),
        (QueryPath('a__b'), slice(0, 1), QueryPath('a')),
        (QueryPath('a__b'), slice(5, 10), QueryPath()),
    ])
    def test_get_item(self, query_path, item, expected_result):
        result = query_path[item]
        assert isinstance(result, expected_result.__class__)
        assert result == expected_result

    def test_string_representation(self):
        query_path = QueryPath(('a', 'b', 'c'))
        assert six.text_type(query_path) == 'a__b__c'

    def test_representation(self):
        query_path = QueryPath(('a', 'b'))
        assert repr(query_path) == '<QueryPath: a__b>'

    def test_build_filter(self):
        path = 'a__b__c'
        value = 1337
        query_path = QueryPath(path)
        condition = query_path.build_filter(value)
        assert isinstance(condition, Q)
        assert len(condition.children) == 1
        assert condition.children[0] == (path, value)


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

    @pytest.mark.parametrize('base_class, mixin_class', [
        (DummyClass, DummyMixin),
        (DummyClass, DummyMixinWithMetaclass),
        (DummyClassWithMetaclass, DummyMixin),
        (DummyClassWithMetaclass, DummyMixinWithMetaclass),
    ])
    def test_mix_with_class_metaclasses(self, base_class, mixin_class):
        cls = mixin_class.mix_with_class(base_class)
        assert issubclass(cls, base_class)
        assert issubclass(cls, mixin_class)
        assert isinstance(cls, base_class.__class__)
        assert isinstance(cls, mixin_class.__class__)

    def test_inject_into_object(self):
        obj = DummyClass(5, 'abc')
        assert DummyMixin.inject_into_object(obj) is obj
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

    @pytest.mark.parametrize('path, expected_query_path', [
        ('attr', QueryPath('attr')),
        ('attr1.attr2', QueryPath('attr1__attr2')),
        ('attr1.attr2.attr3', QueryPath('attr1__attr2__attr3')),
    ])
    def test_initializer(self, path, expected_query_path):
        getter = ModelAttributeGetter(path)
        assert getter.query_path == expected_query_path

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
        assert len(condition.children) == 1
        assert condition.children[0] == (expected_query_name, value)


def test_parametrizable_decorator():

    @decorator
    def func1():
        pass

    @decorator(some_kwarg=1, another_kwarg='test')
    def func2():
        pass

    def func3():
        pass

    func3 = decorator(func3, 1, 2, kwarg='test')

    assert func1.args == ()
    assert func1.kwargs == {}
    assert func2.args == ()
    assert func2.kwargs == dict(some_kwarg=1, another_kwarg='test')
    assert func3.args == (1, 2)
    assert func3.kwargs == dict(kwarg='test')


class TestResolveQueryableProperty(object):

    @pytest.mark.parametrize('model, query_path, expected_property, expected_lookups', [
        # No relation involved
        (VersionWithClassBasedProperties, QueryPath('version'), VersionWithClassBasedProperties.version, QueryPath()),
        (VersionWithDecoratorBasedProperties, QueryPath('version'),
         VersionWithDecoratorBasedProperties.version, QueryPath()),
        (VersionWithClassBasedProperties, QueryPath('version__lower__exact'),
         VersionWithClassBasedProperties.version, QueryPath('lower__exact')),
        (VersionWithDecoratorBasedProperties, QueryPath('version__lower__exact'),
         VersionWithDecoratorBasedProperties.version, QueryPath('lower__exact')),
        # FK forward relation
        (VersionWithClassBasedProperties, QueryPath('application__version_count'),
         ApplicationWithClassBasedProperties.version_count, QueryPath()),
        (VersionWithDecoratorBasedProperties, QueryPath('application__version_count'),
         ApplicationWithDecoratorBasedProperties.version_count, QueryPath()),
        (VersionWithClassBasedProperties, QueryPath('application__major_sum__gt'),
         ApplicationWithClassBasedProperties.major_sum, QueryPath('gt')),
        (VersionWithDecoratorBasedProperties, QueryPath('application__major_sum__gt'),
         ApplicationWithDecoratorBasedProperties.major_sum, QueryPath('gt')),
        # FK reverse relation
        (ApplicationWithClassBasedProperties, QueryPath('versions__major_minor'),
         VersionWithClassBasedProperties.major_minor, QueryPath()),
        (ApplicationWithDecoratorBasedProperties, QueryPath('versions__major_minor'),
         VersionWithDecoratorBasedProperties.major_minor, QueryPath()),
        (ApplicationWithClassBasedProperties, QueryPath('versions__version__lower__contains'),
         VersionWithClassBasedProperties.version, QueryPath('lower__contains')),
        (ApplicationWithDecoratorBasedProperties, QueryPath('versions__version__lower__contains'),
         VersionWithDecoratorBasedProperties.version, QueryPath('lower__contains')),
        # M2M forward relation
        (ApplicationWithClassBasedProperties, QueryPath('categories__circular'),
         CategoryWithClassBasedProperties.circular, QueryPath()),
        (ApplicationWithDecoratorBasedProperties, QueryPath('categories__circular'),
         CategoryWithDecoratorBasedProperties.circular, QueryPath()),
        (ApplicationWithClassBasedProperties, QueryPath('categories__circular__exact'),
         CategoryWithClassBasedProperties.circular, QueryPath('exact')),
        (ApplicationWithDecoratorBasedProperties, QueryPath('categories__circular__exact'),
         CategoryWithDecoratorBasedProperties.circular, QueryPath('exact')),
        # M2M reverse relation
        (CategoryWithClassBasedProperties, QueryPath('applications__major_sum'),
         ApplicationWithClassBasedProperties.major_sum, QueryPath()),
        (CategoryWithDecoratorBasedProperties, QueryPath('applications__major_sum'),
         ApplicationWithDecoratorBasedProperties.major_sum, QueryPath()),
        (CategoryWithClassBasedProperties, QueryPath('applications__version_count__lt'),
         ApplicationWithClassBasedProperties.version_count, QueryPath('lt')),
        (CategoryWithDecoratorBasedProperties, QueryPath('applications__version_count__lt'),
         ApplicationWithDecoratorBasedProperties.version_count, QueryPath('lt')),
        # Multiple relations
        (CategoryWithClassBasedProperties, QueryPath('applications__versions__application__categories__circular'),
         CategoryWithClassBasedProperties.circular, QueryPath()),
        (CategoryWithDecoratorBasedProperties, QueryPath('applications__versions__application__categories__circular'),
         CategoryWithDecoratorBasedProperties.circular, QueryPath()),
        (VersionWithClassBasedProperties, QueryPath('application__categories__circular__in'),
         CategoryWithClassBasedProperties.circular, QueryPath('in')),
        (VersionWithDecoratorBasedProperties, QueryPath('application__categories__circular__in'),
         CategoryWithDecoratorBasedProperties.circular, QueryPath('in')),
    ])
    def test_successful(self, model, query_path, expected_property, expected_lookups):
        expected_ref = QueryablePropertyReference(expected_property, expected_property.model,
                                                  query_path[:-len(expected_lookups) - 1])
        assert resolve_queryable_property(model, query_path) == (expected_ref, expected_lookups)

    @pytest.mark.parametrize('model, query_path', [
        # No relation involved
        (VersionWithClassBasedProperties, QueryPath('non_existent')),
        (VersionWithDecoratorBasedProperties, QueryPath('non_existent')),
        (VersionWithClassBasedProperties, QueryPath('major')),
        (VersionWithDecoratorBasedProperties, QueryPath('major')),
        # FK forward relation
        (VersionWithClassBasedProperties, QueryPath('application__non_existent__exact')),
        (VersionWithDecoratorBasedProperties, QueryPath('application__non_existent__exact')),
        (VersionWithClassBasedProperties, QueryPath('application__name')),
        (VersionWithDecoratorBasedProperties, QueryPath('application__name')),
        # FK reverse relation
        (ApplicationWithClassBasedProperties, QueryPath('versions__non_existent')),
        (ApplicationWithDecoratorBasedProperties, QueryPath('versions__non_existent')),
        (ApplicationWithClassBasedProperties, QueryPath('versions__minor__gt')),
        (ApplicationWithDecoratorBasedProperties, QueryPath('versions__minor__gt')),
        # M2M forward relation
        (ApplicationWithClassBasedProperties, QueryPath('categories__non_existent')),
        (ApplicationWithDecoratorBasedProperties, QueryPath('categories__non_existent')),
        (ApplicationWithClassBasedProperties, QueryPath('categories__name')),
        (ApplicationWithDecoratorBasedProperties, QueryPath('categories__name')),
        # M2M reverse relation
        (CategoryWithClassBasedProperties, QueryPath('applications__non_existent')),
        (CategoryWithDecoratorBasedProperties, QueryPath('applications__non_existent')),
        (CategoryWithClassBasedProperties, QueryPath('applications__name')),
        (CategoryWithDecoratorBasedProperties, QueryPath('applications__name')),
        # Non existent relation
        (VersionWithClassBasedProperties, QueryPath('non_existent_relation__non_existent__in')),
        (VersionWithDecoratorBasedProperties, QueryPath('non_existent_relation__non_existent__in')),
    ])
    def test_unsuccessful(self, model, query_path):
        assert resolve_queryable_property(model, query_path) == (None, QueryPath())


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
