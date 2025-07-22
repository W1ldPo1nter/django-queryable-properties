# encoding: utf-8
from collections import OrderedDict

import pytest
import six
from django import VERSION as DJANGO_VERSION
from django.db.models import CharField, Q, QuerySet

from queryable_properties.exceptions import QueryablePropertyError
from queryable_properties.properties import (
    REMAINING_LOOKUPS, AnnotationGetterMixin, AnnotationMixin, LookupFilterMixin, QueryableProperty, boolean_filter,
    lookup_filter,
)
from queryable_properties.properties.mixins import IgnoreCacheMixin, InheritanceMixin, SubqueryMixin
from queryable_properties.utils import get_queryable_property, QueryPath
from queryable_properties.utils.internal import get_queryable_property_descriptor
from ..app_management.models import ApplicationWithClassBasedProperties, VersionWithClassBasedProperties
from ..inheritance.models import Child1, Child2, Grandchild1, MultipleChild, MultipleParent1, Parent, ProxyChild
from ..marks import skip_if_no_composite_pks, skip_if_no_expressions


class BaseLookupFilterProperty(LookupFilterMixin, QueryableProperty):

    @boolean_filter
    def filter_boolean(self, cls):
        return Q(dummy__year__gt=2000)

    @lookup_filter('iexact')
    def filter_ci_equality(self, cls, lookup, value):
        return Q(dummy=value)

    @lookup_filter('lt', 'lte')
    def filter_lower(self, cls, lookup, value):
        return Q(**{'dummy__day__{}'.format(lookup): value})


class DerivedLookupFilterProperty(BaseLookupFilterProperty):

    @lookup_filter('lt', 'gt')
    def filter_comparison(self, cls, lookup, value):
        return Q(**{'dummy__month__{}'.format(lookup): value})

    @lookup_filter('in')
    def filter_in(self, cls, lookup, value):
        value = list(value) + ['test']
        return Q(dummy__in=value)


class ParentRemainingLookupFilterProperty(LookupFilterMixin, AnnotationMixin, QueryableProperty):

    remaining_lookups_via_parent = True

    @lookup_filter('exact')
    def filter_equality(self, cls, lookup, value):
        return Q(exact=value)


class MethodRemainingLookupFilterProperty(ParentRemainingLookupFilterProperty):

    @lookup_filter(REMAINING_LOOKUPS)
    def filter_remaining(self, cls, lookup, value):
        return Q(remaining=value)


class TestLookupFilterMixin(object):

    def test_registration(self):
        base = BaseLookupFilterProperty()
        assert set(base.lookup_mappings) == {'exact', 'iexact', 'lt', 'lte'}
        assert base.lookup_mappings['exact'] != base.lookup_mappings['iexact']
        assert base.lookup_mappings['exact'] != base.lookup_mappings['lt']
        assert base.lookup_mappings['iexact'] != base.lookup_mappings['lt']
        assert base.lookup_mappings['lte'] == base.lookup_mappings['lt']

        derived = DerivedLookupFilterProperty()
        assert set(derived.lookup_mappings) == {'exact', 'iexact', 'lt', 'lte', 'gt', 'in'}
        assert derived.lookup_mappings['exact'] != derived.lookup_mappings['lt']
        assert derived.lookup_mappings['exact'] != derived.lookup_mappings['iexact']
        assert derived.lookup_mappings['iexact'] != derived.lookup_mappings['lt']
        assert derived.lookup_mappings['lte'] != derived.lookup_mappings['lt']
        assert derived.lookup_mappings['gt'] == derived.lookup_mappings['lt']

    @pytest.mark.parametrize('cls, lookup, value, expected_q_value, expected_q_negation', [
        (BaseLookupFilterProperty, 'exact', True, ('dummy__year__gt', 2000), False),
        (BaseLookupFilterProperty, 'exact', False, ('dummy__year__gt', 2000), True),
        (BaseLookupFilterProperty, 'iexact', 'test', ('dummy', 'test'), False),
        (BaseLookupFilterProperty, 'lt', 42, ('dummy__day__lt', 42), False),
        (BaseLookupFilterProperty, 'lte', 1337, ('dummy__day__lte', 1337), False),

        (DerivedLookupFilterProperty, 'exact', True, ('dummy__year__gt', 2000), False),
        (DerivedLookupFilterProperty, 'exact', False, ('dummy__year__gt', 2000), True),
        (DerivedLookupFilterProperty, 'iexact', 'test', ('dummy', 'test'), False),
        (DerivedLookupFilterProperty, 'lt', 42, ('dummy__month__lt', 42), False),
        (DerivedLookupFilterProperty, 'gt', 69, ('dummy__month__gt', 69), False),
        (DerivedLookupFilterProperty, 'lte', 1337, ('dummy__day__lte', 1337), False),
        (DerivedLookupFilterProperty, 'in', ('a', 'b'), ('dummy__in', ['a', 'b', 'test']), False),
    ])
    def test_filter_call(self, cls, lookup, value, expected_q_value, expected_q_negation):
        prop = cls()
        q = prop.get_filter(None, lookup, value)
        if DJANGO_VERSION < (1, 6) and expected_q_negation:
            # In very old Django versions, negating adds another layer.
            q = q.children[0]
        assert len(q.children) == 1
        assert q.children[0] == expected_q_value
        assert q.negated is expected_q_negation

    @pytest.mark.parametrize('cls, lookup, value, expected_q_value', [
        (ParentRemainingLookupFilterProperty, 'exact', 1337, ('exact', 1337)),
        (ParentRemainingLookupFilterProperty, 'gt', 42, ('dummy__gt', 42)),
        (ParentRemainingLookupFilterProperty, 'lte', 69, ('dummy__lte', 69)),
        (MethodRemainingLookupFilterProperty, 'exact', 1337, ('exact', 1337)),
        (MethodRemainingLookupFilterProperty, 'gt', 42, ('remaining', 42)),
        (MethodRemainingLookupFilterProperty, 'lte', 69, ('remaining', 69)),
    ])
    def test_remaining_lookups(self, cls, lookup, value, expected_q_value):
        prop = cls()
        prop.model = ApplicationWithClassBasedProperties
        prop.name = 'dummy'
        q = prop.get_filter(None, lookup, value)
        assert len(q.children) == 1
        assert q.children[0] == expected_q_value

    @pytest.mark.parametrize('cls, lookup, value', [
        (BaseLookupFilterProperty, 'month', 5),
        (BaseLookupFilterProperty, 'gt', 42),
        (BaseLookupFilterProperty, 'gte', 42),
        (BaseLookupFilterProperty, 'in', ['a', 'b']),
        (DerivedLookupFilterProperty, 'month', 5),
        (DerivedLookupFilterProperty, 'gte', 42),
    ])
    def test_filter_call_not_implemented(self, cls, lookup, value):
        prop = cls()
        prop.model = ApplicationWithClassBasedProperties
        prop.name = 'dummy'
        with pytest.raises(QueryablePropertyError):
            prop.get_filter(None, lookup, value)


class TestAnnotationMixin(object):

    @pytest.fixture
    def prop(self):
        cls = AnnotationMixin.mix_with_class(QueryableProperty)
        prop = cls()
        prop.name = 'test'
        return prop

    def test_admin_order_field(self, prop):
        assert prop.admin_order_field == 'test'

    @pytest.mark.parametrize('lookup, value', [
        ('exact', 'abc'),
        ('isnull', True),
        ('lte', 5),
    ])
    def test_get_filter(self, prop, lookup, value):
        q = prop.get_filter(ApplicationWithClassBasedProperties, lookup, value)
        assert isinstance(q, Q)
        assert len(q.children) == 1
        assert q.children[0] == ('test__{}'.format(lookup), value)


class TestAnnotationGetterMixin(object):

    @pytest.fixture
    def prop(self):
        prop = get_queryable_property(ApplicationWithClassBasedProperties, 'version_count')
        assert isinstance(prop, AnnotationGetterMixin)
        return prop

    @pytest.fixture
    def nested_prop(self):
        prop = get_queryable_property(ApplicationWithClassBasedProperties, 'major_avg')
        assert isinstance(prop, AnnotationGetterMixin)
        return prop

    @pytest.mark.parametrize('kwargs, expected_cached', [
        ({}, QueryableProperty.cached),
        ({'cached': None}, QueryableProperty.cached),
        ({'cached': False}, False),
        ({'cached': True}, True),
    ])
    def test_initializer(self, kwargs, expected_cached):
        cls = AnnotationGetterMixin.mix_with_class(QueryableProperty)
        prop = cls(**kwargs)
        assert prop.cached is expected_cached

    @pytest.mark.django_db
    def test_get_queryset(self, prop, applications):
        assert set(prop.get_queryset(ApplicationWithClassBasedProperties)) == set(applications[:2])

    @pytest.mark.django_db
    def test_get_queryset_for_object(self, prop, applications):
        for application in applications[:2]:
            assert prop.get_queryset_for_object(application).get() == application

    @skip_if_no_composite_pks
    @pytest.mark.django_db
    def test_get_queryset_for_object_composite_pk(self, download_links):
        prop = get_queryable_property(download_links[0].__class__, 'alternative')
        assert isinstance(prop, AnnotationGetterMixin)
        for download_link in download_links[:3]:
            assert isinstance(download_link.pk, tuple)
            assert prop.get_queryset_for_object(download_link).get() == download_link

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    def test_get_value(self, prop, applications):
        for application in applications[:2]:
            assert prop.get_value(application) == 4

    @pytest.mark.skipif(DJANGO_VERSION < (1, 10), reason="The Cast() expression didn't exist before Django 1.10")
    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    def test_get_value_nested_properties(self, nested_prop, applications):
        for application in applications[:2]:
            assert nested_prop.get_value(application) == 1.25

    @pytest.mark.django_db
    def test_get_value_unsaved_object(self, prop):
        application = ApplicationWithClassBasedProperties()
        with pytest.raises(ApplicationWithClassBasedProperties.DoesNotExist):
            prop.get_value(application)


class TestSubqueryMixin(object):

    @pytest.mark.parametrize('kwargs', [
        {},
        {'cached': True},
        {'queryset': ApplicationWithClassBasedProperties.objects.filter(name='test')},
        {'queryset': ApplicationWithClassBasedProperties.objects.all(), 'cached': True}
    ])
    def test_initializer(self, kwargs):
        cls = SubqueryMixin.mix_with_class(QueryableProperty)
        prop = cls(**kwargs)
        assert prop._inner_queryset is kwargs.get('queryset')
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)

    @pytest.mark.parametrize('queryset, expected_model', [
        (ApplicationWithClassBasedProperties.objects.all(), ApplicationWithClassBasedProperties),
        (lambda: ApplicationWithClassBasedProperties.objects.all(), ApplicationWithClassBasedProperties),
        (lambda model: model.objects.all(), VersionWithClassBasedProperties),
    ])
    def test_get_inner_queryset(self, queryset, expected_model):
        cls = SubqueryMixin.mix_with_class(QueryableProperty)
        prop = cls(queryset)
        result = prop._get_inner_queryset(VersionWithClassBasedProperties)
        assert isinstance(result, QuerySet)
        assert result.model is expected_model


class TestInheritanceMixin(object):

    @pytest.mark.parametrize('kwargs', [
        {},
        {'cached': True},
        {'depth': 2},
        {'depth': 3, 'cached': True}
    ])
    def test_initializer(self, kwargs):
        cls = InheritanceMixin.mix_with_class(QueryableProperty)
        prop = cls(**kwargs)
        assert prop.depth == kwargs.get('depth')
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)

    def test_get_condition_for_model(self):
        result = InheritanceMixin()._get_condition_for_model(Grandchild1, QueryPath('child1__grandchild1'))
        assert isinstance(result, Q)
        assert result.children == [('child1__grandchild1__isnull', False)]

    @skip_if_no_expressions
    @pytest.mark.parametrize('model, expected_result, expected_cache', [
        (Grandchild1, OrderedDict(), {Grandchild1: OrderedDict()}),
        (
            Child1,
            OrderedDict([(Grandchild1, QueryPath('grandchild1'))]),
            {
                Grandchild1: OrderedDict(),
                Child1: OrderedDict([(Grandchild1, QueryPath('grandchild1'))]),
            },
        ),
        (
            ProxyChild,
            OrderedDict([(Grandchild1, QueryPath('grandchild1'))]),
            {
                Grandchild1: OrderedDict(),
                Child1: OrderedDict([(Grandchild1, QueryPath('grandchild1'))]),
            },
        ),
        (
            Parent,
            OrderedDict([
                (Grandchild1, QueryPath('child1__grandchild1')),
                (Child1, QueryPath('child1')),
                (Child2, QueryPath('child2')),
            ]),
            {
                Grandchild1: OrderedDict(),
                Child2: OrderedDict(),
                Child1: OrderedDict([(Grandchild1, QueryPath('grandchild1'))]),
                Parent: OrderedDict([
                    (Grandchild1, QueryPath('child1__grandchild1')),
                    (Child1, QueryPath('child1')),
                    (Child2, QueryPath('child2')),
                ]),
            },
        ),
        (
            MultipleParent1,
            OrderedDict([(MultipleChild, QueryPath('multiplechild'))]),
            {
                MultipleChild: OrderedDict(),
                MultipleParent1: OrderedDict([(MultipleChild, QueryPath('multiplechild'))]),
            },
        ),
    ])
    def test_get_child_paths(self, model, expected_result, expected_cache):
        prop = InheritanceMixin.mix_with_class(QueryableProperty)()
        prop._child_paths = {}
        assert prop._get_child_paths(model) == expected_result
        assert prop._child_paths == expected_cache

    @skip_if_no_expressions
    @pytest.mark.parametrize('depth', [None, 2, 1, 0])
    def test_build_case_expression(self, depth):
        from django.db.models import Case, Value, When

        prop = InheritanceMixin.mix_with_class(QueryableProperty)(depth=depth)
        prop._child_paths = {Parent: OrderedDict((
            (Grandchild1, QueryPath('child1__grandchild1')),
            (Child1, QueryPath('child1')),
        ))}
        prop._inheritance_output_field = CharField()
        prop._get_value_for_model = lambda model: model.__name__
        if depth == 0:
            expected_conditions = []
        else:
            expected_conditions = [((query_path + 'isnull').as_str(), False) for query_path
                                   in six.itervalues(prop._child_paths[Parent])]
            if depth is not None:
                expected_conditions = expected_conditions[-depth:]

        case = prop._build_case_expression(Parent)
        assert isinstance(case, Case)
        assert len(case.cases) == len(expected_conditions)
        for when, expected_condition in zip(case.cases, expected_conditions):
            assert isinstance(when, When)
            assert when.condition.children == [expected_condition]
        assert isinstance(case.default, Value)
        assert case.default.value == 'Parent'
        assert case.output_field is prop._inheritance_output_field


class TestIgnoreCacheMixin(object):

    @pytest.fixture
    def prop(self):
        return type('DummyIgnoreCacheProperty', (IgnoreCacheMixin, QueryableProperty), {})()

    def test_initializer(self, prop):
        assert prop._descriptor is None

    def test_contribute_to_class(self, prop):
        class DummyModel(object):
            pass

        prop.contribute_to_class(DummyModel, 'dummy')
        assert prop._descriptor is get_queryable_property_descriptor(DummyModel, 'dummy')
        assert prop._descriptor._ignore_cached_value is True
