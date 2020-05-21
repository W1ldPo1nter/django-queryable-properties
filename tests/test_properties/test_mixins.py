# encoding: utf-8
import pytest

from django import VERSION as DJANGO_VERSION
from django.db.models import Q

from queryable_properties.exceptions import QueryablePropertyError
from queryable_properties.properties import (AnnotationMixin, boolean_filter, LookupFilterMixin, lookup_filter,
                                             QueryableProperty)

from ..models import ApplicationWithClassBasedProperties


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
