# encoding: utf-8
from collections import Counter

import pytest
import six
from django import VERSION as DJANGO_VERSION
from django.db.models import CharField, Count, IntegerField, Q, Sum
from six.moves import cPickle

from queryable_properties.exceptions import QueryablePropertyDoesNotExist, QueryablePropertyError
from queryable_properties.properties.base import QueryablePropertyDescriptor
from queryable_properties.utils import get_queryable_property
from queryable_properties.utils.internal import (
    MISSING_OBJECT, InjectableMixin, ModelAttributeGetter, NodeChecker, NodeModifier, NodeProcessor,
    QueryablePropertyReference, QueryPath, get_output_field, get_queryable_property_descriptor,
    parametrizable_decorator, resolve_queryable_property,
)
from ..app_management.models import (
    ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties, CategoryWithClassBasedProperties,
    CategoryWithDecoratorBasedProperties, VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties,
)
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
            # Test that trying to mix in the class a second time returns the
            # base class unchanged.
            assert cls is DummyMixin.mix_with_class(cls)
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

    @pytest.mark.parametrize('init', [True, False])
    def test_inject_into_object(self, init):
        obj = DummyClass(5, 'abc')
        obj.mixin_attr1 = obj.mixin_attr2 = None
        assert DummyMixin.inject_into_object(obj, init=init) is obj
        assert isinstance(obj, DummyClass)
        assert isinstance(obj, DummyMixin)
        assert obj.attr1 == 5
        assert obj.attr2 == 'abc'
        assert obj.mixin_attr1 == (1.337 if init else None)
        assert obj.mixin_attr2 == ('test' if init else None)
        # Test that init_injected_attrs is not called when no injection takes
        # places due to the object already using the mixin.
        obj.mixin_attr1 = obj.mixin_attr2 = None
        DummyMixin.inject_into_object(obj)
        assert obj.mixin_attr1 is obj.mixin_attr2 is None

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


class TestNodeProcessor(object):

    def test_initializer(self):
        def func(item):
            return item

        processor = NodeProcessor(func)
        assert processor.func is func

    def test_iter_leaves(self):
        processor = NodeProcessor(lambda item: item)
        inner_q = Q(a=1) | Q(b=2)
        outer_q = Q(inner_q, c=3)
        assert list(processor.iter_leaves(outer_q)) == [
            (inner_q, 0, ('a', 1)),
            (inner_q, 1, ('b', 2)),
            (outer_q, 1, ('c', 3)),
        ]


class TestNodeChecker(object):

    @pytest.mark.parametrize('node, path, expected_result', [
        (Q(a=1), 'a', True),
        (Q(b=2), 'a', False),
        (Q(a=1), 'b', False),
        (Q(b=2), 'b', True),
        (Q(Q(a=1) | Q(b=2), c=3), 'a', True),
        (Q(Q(a=1) | Q(b=2), c=3), 'c', True),
        (Q(Q(a=1) | Q(b=2), c=3), 'd', False),
    ])
    def test_check_leaves(self, node, path, expected_result):
        # The predicate checks if a leaf for a given path exists
        checker = NodeChecker(lambda item, required_path: item[0] == path)
        assert checker.check_leaves(node, required_path=path) is expected_result


class TestNodeModifier(object):

    @pytest.mark.parametrize('copy', [True, False])
    @pytest.mark.parametrize('increment, expected_a, expected_b, expected_c', [
        (1, 2, 3, 4),
        (10, 11, 12, 13),
    ])
    def test_modify_leaves(self, copy, increment, expected_a, expected_b, expected_c):
        modifier = NodeModifier(lambda item, inc: ('new_{}'.format(item[0]), item[1] + inc))
        q = Q(Q(a=1) | Q(b=2), c=3)
        result = modifier.modify_leaves(q, copy, inc=increment)
        assert (result is q) is not copy
        assert len(result.children) == 2
        assert result.children[0].children == [('new_a', expected_a), ('new_b', expected_b)]
        assert result.children[1] == ('new_c', expected_c)


class TestModelAttributeGetter(object):

    @pytest.mark.parametrize('path, expected_query_path', [
        ('attr', QueryPath('attr')),
        ('attr1.attr2', QueryPath('attr1__attr2')),
        ('attr1.attr2.attr3', QueryPath('attr1__attr2__attr3')),
        (['attr1', 'attr2'], QueryPath('attr1__attr2')),
        (('attr1', 'attr2', 'attr3'), QueryPath('attr1__attr2__attr3')),
    ])
    def test_initializer(self, path, expected_query_path):
        getter = ModelAttributeGetter(path)
        assert getter.query_path == expected_query_path

    @pytest.mark.django_db
    @pytest.mark.parametrize('attribute_name, expected_value', [
        ('major', 1),
        ('changes', None),
    ])
    def test_get_attribute(self, versions, attribute_name, expected_value):
        getter = ModelAttributeGetter(())
        assert getter._get_attribute(versions[0], attribute_name) == expected_value

    def test_get_attribute_catch_attribute_error_on_none(self):
        getter = ModelAttributeGetter(())
        assert getter._get_attribute(None, 'non_existent') is MISSING_OBJECT

    @pytest.mark.django_db
    def test_get_attribute_bubble_attribute_error(self, versions):
        getter = ModelAttributeGetter(())
        with pytest.raises(AttributeError):
            getter._get_attribute(versions[0], 'non_existent')

    @pytest.mark.django_db
    def test_get_attribute_catch_object_does_not_exist(self, applications, versions):
        obj = versions[0].__class__.objects.get(pk=versions[0].pk)  # Refresh from DB
        applications[0].delete()
        getter = ModelAttributeGetter(())
        assert getter._get_attribute(obj, 'application') is MISSING_OBJECT

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
    def test_get_value_missing_object(self, applications, versions):
        obj = versions[0].__class__.objects.get(pk=versions[0].pk)  # Refresh from DB
        applications[0].delete()
        getter = ModelAttributeGetter('application.name')
        assert getter.get_value(obj) is MISSING_OBJECT

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    def test_get_values(self, categories):
        getter = ModelAttributeGetter('applications.versions.major')
        assert Counter(getter.get_values(categories[0])) == Counter({2: 2, 1: 6})

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    def test_get_values_missing_object(self, categories):
        getter = ModelAttributeGetter('applications.versions.major')
        VersionWithClassBasedProperties.objects.all().delete()
        assert getter.get_values(categories[0]) == []
        ApplicationWithClassBasedProperties.objects.all().delete()
        assert getter.get_values(categories[0]) == []

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


class TestGetQueryablePropertyDescriptor(object):

    @pytest.mark.parametrize('model, property_name', [
        (VersionWithClassBasedProperties, 'major_minor'),
        (VersionWithDecoratorBasedProperties, 'major_minor'),
        (VersionWithClassBasedProperties, 'version'),
        (VersionWithDecoratorBasedProperties, 'version'),
    ])
    def test_property_found(self, model, property_name):
        descriptor = get_queryable_property_descriptor(model, property_name)
        assert isinstance(descriptor, QueryablePropertyDescriptor)

    @pytest.mark.parametrize('model, property_name', [
        (VersionWithClassBasedProperties, 'non_existent'),
        (VersionWithDecoratorBasedProperties, 'non_existent'),
        (VersionWithClassBasedProperties, 'major'),  # Existing model field
        (VersionWithDecoratorBasedProperties, 'major'),  # Existing model field
    ])
    def test_exception(self, model, property_name):
        with pytest.raises(QueryablePropertyDoesNotExist):
            get_queryable_property_descriptor(model, property_name)


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


class TestResolveQueryableProperty(object):

    @pytest.mark.parametrize('model, query_path, expected_property, expected_lookups', [
        # No relation involved
        (VersionWithClassBasedProperties, QueryPath('version'),
         get_queryable_property(VersionWithClassBasedProperties, 'version'), QueryPath()),
        (VersionWithDecoratorBasedProperties, QueryPath('version'),
         get_queryable_property(VersionWithDecoratorBasedProperties, 'version'), QueryPath()),
        (VersionWithClassBasedProperties, QueryPath('version__lower__exact'),
         get_queryable_property(VersionWithClassBasedProperties, 'version'), QueryPath('lower__exact')),
        (VersionWithDecoratorBasedProperties, QueryPath('version__lower__exact'),
         get_queryable_property(VersionWithDecoratorBasedProperties, 'version'), QueryPath('lower__exact')),
        # FK forward relation
        (VersionWithClassBasedProperties, QueryPath('application__version_count'),
         get_queryable_property(ApplicationWithClassBasedProperties, 'version_count'), QueryPath()),
        (VersionWithDecoratorBasedProperties, QueryPath('application__version_count'),
         get_queryable_property(ApplicationWithDecoratorBasedProperties, 'version_count'), QueryPath()),
        (VersionWithClassBasedProperties, QueryPath('application__major_sum__gt'),
         get_queryable_property(ApplicationWithClassBasedProperties, 'major_sum'), QueryPath('gt')),
        (VersionWithDecoratorBasedProperties, QueryPath('application__major_sum__gt'),
         get_queryable_property(ApplicationWithDecoratorBasedProperties, 'major_sum'), QueryPath('gt')),
        # FK reverse relation
        (ApplicationWithClassBasedProperties, QueryPath('versions__major_minor'),
         get_queryable_property(VersionWithClassBasedProperties, 'major_minor'), QueryPath()),
        (ApplicationWithDecoratorBasedProperties, QueryPath('versions__major_minor'),
         get_queryable_property(VersionWithDecoratorBasedProperties, 'major_minor'), QueryPath()),
        (ApplicationWithClassBasedProperties, QueryPath('versions__version__lower__contains'),
         get_queryable_property(VersionWithClassBasedProperties, 'version'), QueryPath('lower__contains')),
        (ApplicationWithDecoratorBasedProperties, QueryPath('versions__version__lower__contains'),
         get_queryable_property(VersionWithDecoratorBasedProperties, 'version'), QueryPath('lower__contains')),
        # M2M forward relation
        (ApplicationWithClassBasedProperties, QueryPath('categories__circular'),
         get_queryable_property(CategoryWithClassBasedProperties, 'circular'), QueryPath()),
        (ApplicationWithDecoratorBasedProperties, QueryPath('categories__circular'),
         get_queryable_property(CategoryWithDecoratorBasedProperties, 'circular'), QueryPath()),
        (ApplicationWithClassBasedProperties, QueryPath('categories__circular__exact'),
         get_queryable_property(CategoryWithClassBasedProperties, 'circular'), QueryPath('exact')),
        (ApplicationWithDecoratorBasedProperties, QueryPath('categories__circular__exact'),
         get_queryable_property(CategoryWithDecoratorBasedProperties, 'circular'), QueryPath('exact')),
        # M2M reverse relation
        (CategoryWithClassBasedProperties, QueryPath('applications__major_sum'),
         get_queryable_property(ApplicationWithClassBasedProperties, 'major_sum'), QueryPath()),
        (CategoryWithDecoratorBasedProperties, QueryPath('applications__major_sum'),
         get_queryable_property(ApplicationWithDecoratorBasedProperties, 'major_sum'), QueryPath()),
        (CategoryWithClassBasedProperties, QueryPath('applications__version_count__lt'),
         get_queryable_property(ApplicationWithClassBasedProperties, 'version_count'), QueryPath('lt')),
        (CategoryWithDecoratorBasedProperties, QueryPath('applications__version_count__lt'),
         get_queryable_property(ApplicationWithDecoratorBasedProperties, 'version_count'), QueryPath('lt')),
        # Multiple relations
        (CategoryWithClassBasedProperties, QueryPath('applications__versions__application__categories__circular'),
         get_queryable_property(CategoryWithClassBasedProperties, 'circular'), QueryPath()),
        (CategoryWithDecoratorBasedProperties, QueryPath('applications__versions__application__categories__circular'),
         get_queryable_property(CategoryWithDecoratorBasedProperties, 'circular'), QueryPath()),
        (VersionWithClassBasedProperties, QueryPath('application__categories__circular__in'),
         get_queryable_property(CategoryWithClassBasedProperties, 'circular'), QueryPath('in')),
        (VersionWithDecoratorBasedProperties, QueryPath('application__categories__circular__in'),
         get_queryable_property(CategoryWithDecoratorBasedProperties, 'circular'), QueryPath('in')),
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
