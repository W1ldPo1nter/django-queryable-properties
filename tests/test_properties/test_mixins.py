# encoding: utf-8
import pytest

from django.db.models import Q

from queryable_properties.properties import AnnotationMixin

from ..models import ApplicationWithClassBasedProperties


class TestAnnotationMixin(object):

    @pytest.fixture
    def mixin_instance(self):
        instance = AnnotationMixin()
        instance.name = 'test'
        return instance

    @pytest.mark.parametrize('lookup, value', [
        ('exact', 'abc'),
        ('isnull', True),
        ('lte', 5),
    ])
    def test_get_filter(self, mixin_instance, lookup, value):
        q = mixin_instance.get_filter(ApplicationWithClassBasedProperties, lookup, value)
        assert isinstance(q, Q)
        assert len(q.children) == 1
        q_expression, q_value = q.children[0]
        assert q_expression == 'test__{}'.format(lookup)
        assert q_value == value
