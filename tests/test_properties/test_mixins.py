# encoding: utf-8
import pytest
from django import VERSION as DJANGO_VERSION
from django.db.models import Q
from mock import patch

from queryable_properties.exceptions import QueryablePropertyError
from queryable_properties.properties import (
    REMAINING_LOOKUPS, AnnotationGetterMixin, AnnotationMixin, LookupFilterMixin, QueryableProperty, boolean_filter,
    lookup_filter,
)
from queryable_properties.properties.mixins import SubqueryMixin
from queryable_properties.utils import get_queryable_property
from ..app_management.models import ApplicationWithClassBasedProperties


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


@pytest.mark.skipif(DJANGO_VERSION < (1, 11), reason="Explicit subqueries didn't exist before Django 1.11")
class TestSubqueryMixin(object):

    @pytest.mark.parametrize('kwargs', [
        {'queryset': ApplicationWithClassBasedProperties.objects.filter(name='test')},
        {'queryset': ApplicationWithClassBasedProperties.objects.all(), 'cached': True}
    ])
    def test_initializer(self, kwargs):
        cls = SubqueryMixin.mix_with_class(QueryableProperty)
        prop = cls(**kwargs)
        assert prop.queryset is kwargs['queryset']
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)

    @pytest.mark.parametrize('use_function', [False, True])
    def test_get_annotation(self, use_function):
        cls = SubqueryMixin.mix_with_class(QueryableProperty)
        queryset = ApplicationWithClassBasedProperties.objects.all()
        prop = cls((lambda: queryset) if use_function else queryset)
        with patch.object(prop, '_build_subquery') as mock_build_queryset:
            assert prop.get_annotation(ApplicationWithClassBasedProperties) == mock_build_queryset.return_value
            mock_build_queryset.assert_called_once_with(queryset)
