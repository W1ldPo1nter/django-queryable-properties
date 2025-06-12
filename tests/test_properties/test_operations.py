# -*- coding: utf-8 -*-
import pytest
from mock import Mock, patch

from queryable_properties.managers import QueryablePropertiesQuerySet
from queryable_properties.properties.operations import QuerySetOperation, SelectRelatedOperation
from tests.inheritance.models import Parent


class TestQuerySetOperation(object):

    @pytest.mark.parametrize('is_applicable', [True, False])
    def test_call(self, is_applicable):
        operation = QuerySetOperation()
        queryset = Mock(spec=QueryablePropertiesQuerySet)
        with patch.object(operation, 'is_applicable', return_value=is_applicable) as mock_is_applicable:
            with patch.object(operation, 'execute') as mock_execute:
                operation(queryset)
        mock_is_applicable.assert_called_once_with(queryset)
        if is_applicable:
            mock_execute.assert_called_once_with(queryset)
        else:
            mock_execute.assert_not_called()


class TestSelectRelatedOperation(object):

    @pytest.mark.parametrize('fields, queryset, expected_result', [
        ((), Parent.objects.all(), False),
        (('child1', 'child2'), Parent.objects.select_related(), False),
        (('child1',), Parent.objects.values('parent_field'), False),
        (
            ('child2',),
            getattr(Parent.objects.all(), 'union', lambda qs: qs.select_related())(Parent.objects.all()),
            False,
        ),
        (('child1', 'child2'), Parent.objects.all(), True),
        (('child1',), Parent.objects.select_related('child2'), True),
    ])
    def test_is_applicable(self, fields, queryset, expected_result):
        operation = SelectRelatedOperation(*fields)
        assert operation.is_applicable(queryset) is expected_result

    @pytest.mark.parametrize('queryset', [
        Parent.objects.all(),
        Parent.objects.select_related('child2'),
        Parent.objects.select_related('child1', 'child2'),
    ])
    def test_execute(self, queryset):
        operation = SelectRelatedOperation('child1', 'child2')
        operation.execute(queryset)
        assert queryset.query.select_related == {'child1': {}, 'child2': {}}
