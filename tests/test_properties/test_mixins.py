# encoding: utf-8
import pytest

from django.db.models import Q

from queryable_properties.exceptions import QueryablePropertyError
from queryable_properties.properties import AnnotationMixin, LookupFilterMixin, lookup_filter, QueryableProperty

from ..models import ApplicationWithClassBasedProperties


class BaseLookupFilterProperty(LookupFilterMixin, QueryableProperty):

    @lookup_filter('exact')
    def filter_equality(self, cls, lookup, value):
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
        assert set(base.lookup_mappings) == {'exact', 'lt', 'lte'}
        assert base.lookup_mappings['exact'] != base.lookup_mappings['lt']
        assert base.lookup_mappings['lte'] == base.lookup_mappings['lt']

        derived = DerivedLookupFilterProperty()
        assert set(derived.lookup_mappings) == {'exact', 'lt', 'lte', 'gt', 'in'}
        assert derived.lookup_mappings['exact'] != derived.lookup_mappings['lt']
        assert derived.lookup_mappings['lte'] != derived.lookup_mappings['lt']
        assert derived.lookup_mappings['gt'] == derived.lookup_mappings['lt']

    @pytest.mark.parametrize('cls, lookup, value, expected_q_value', [
        (BaseLookupFilterProperty, 'exact', 5, ('dummy', 5)),
        (BaseLookupFilterProperty, 'lt', 42, ('dummy__day__lt', 42)),
        (BaseLookupFilterProperty, 'lte', 1337, ('dummy__day__lte', 1337)),

        (DerivedLookupFilterProperty, 'exact', 5, ('dummy', 5)),
        (DerivedLookupFilterProperty, 'lt', 42, ('dummy__month__lt', 42)),
        (DerivedLookupFilterProperty, 'gt', 69, ('dummy__month__gt', 69)),
        (DerivedLookupFilterProperty, 'lte', 1337, ('dummy__day__lte', 1337)),
        (DerivedLookupFilterProperty, 'in', ('a', 'b'), ('dummy__in', ['a', 'b', 'test'])),
    ])
    def test_filter_call(self, cls, lookup, value, expected_q_value):
        prop = cls()
        q = prop.get_filter(None, lookup, value)
        assert len(q.children) == 1
        assert q.children[0] == expected_q_value

    @pytest.mark.parametrize('cls, lookup, value', [
        (BaseLookupFilterProperty, 'iexact', 5),
        (BaseLookupFilterProperty, 'gt', 42),
        (BaseLookupFilterProperty, 'gte', 42),
        (BaseLookupFilterProperty, 'in', ['a', 'b']),
        (DerivedLookupFilterProperty, 'iexact', 5),
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
