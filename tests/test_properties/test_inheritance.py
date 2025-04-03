# -*- coding: utf-8 -*-
from collections import OrderedDict

import pytest
from django import VERSION as DJANGO_VERSION
from django.db.models import CharField

from queryable_properties.properties import InheritanceModelProperty, QueryableProperty
from queryable_properties.utils import get_queryable_property
from queryable_properties.utils.internal import QueryPath
from ..inheritance.models import (
    Child1, Child2, DisconnectedGrandchild2, Grandchild1, MultipleChild, MultipleParent1, Parent, ProxyChild,
)
from ..marks import skip_if_no_expressions


@skip_if_no_expressions
class TestInheritanceModelProperty(object):

    @pytest.mark.parametrize('kwargs', [
        {
            'value_generator': lambda cls: str(cls),
            'output_field': CharField(),
        },
        {
            'value_generator': lambda cls: str(cls),
            'output_field': CharField(),
            'cached': True,
            'verbose_name': 'Test',
        },
    ])
    def test_initializer(self, kwargs):
        prop = InheritanceModelProperty(**kwargs)
        assert prop.value_generator is kwargs['value_generator']
        assert prop.output_field is kwargs['output_field']
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)
        assert prop.verbose_name == kwargs.get('verbose_name')

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
        prop = InheritanceModelProperty(None, None)
        prop._child_paths = {}
        assert prop._get_child_paths(model) == expected_result
        assert prop._child_paths == expected_cache

    @pytest.mark.django_db
    def test_annotation(self, django_assert_num_queries, inheritance_instances):
        with django_assert_num_queries(1):
            instances = Parent.objects.select_properties('plural').in_bulk([
                inheritance_instances[Parent].pk,
                inheritance_instances[Child1].pk,
                inheritance_instances[Child2].pk,
                inheritance_instances[Grandchild1].pk,
                inheritance_instances[DisconnectedGrandchild2].pk,
            ])
            assert instances[inheritance_instances[Parent].pk].plural == 'parents'
            assert instances[inheritance_instances[Child1].pk].plural == 'child1s'
            assert instances[inheritance_instances[Child2].pk].plural == 'child2s'
            assert instances[inheritance_instances[Grandchild1].pk].plural == 'grandchild1s'
            assert instances[inheritance_instances[DisconnectedGrandchild2].pk].plural == 'child2s'

        with django_assert_num_queries(1):
            instances = MultipleParent1.objects.select_properties('plural').in_bulk([
                inheritance_instances[MultipleParent1].pk,
                inheritance_instances[MultipleChild].pk,
            ])
            assert instances[inheritance_instances[MultipleParent1].pk].plural == 'multiple parent1s'
            assert instances[inheritance_instances[MultipleChild].pk].plural == 'multiple childs'

        # In Django versions below 1.10, proxy models seemingly can't access
        # parent links.
        if DJANGO_VERSION >= (1, 10):
            with django_assert_num_queries(1):
                instances = ProxyChild.objects.select_properties('plural').in_bulk([
                    inheritance_instances[Child1].pk,
                    inheritance_instances[Grandchild1].pk,
                ])
                assert instances[inheritance_instances[Child1].pk].plural == 'proxy childs'
                assert instances[inheritance_instances[Grandchild1].pk].plural == 'grandchild1s'

        assert Parent.objects.get(plural='parents') == inheritance_instances[Parent]
        assert Parent.objects.get(plural='grandchild1s').pk == inheritance_instances[Grandchild1].pk

    @pytest.mark.django_db
    @pytest.mark.parametrize('depth, expected_values', [
        (
            None,
            {
                Parent: 'parents',
                Child1: 'child1s',
                Child2: 'child2s',
                Grandchild1: 'grandchild1s',
                DisconnectedGrandchild2: 'child2s',
            },
        ),
        (
            2,
            {
                Parent: 'parents',
                Child1: 'child1s',
                Child2: 'child2s',
                Grandchild1: 'grandchild1s',
                DisconnectedGrandchild2: 'child2s',
            },
        ),
        (
            1,
            {
                Parent: 'parents',
                Child1: 'child1s',
                Child2: 'child2s',
                Grandchild1: 'child1s',
                DisconnectedGrandchild2: 'child2s',
            },
        ),
        (
            0,
            {
                Parent: 'parents',
                Child1: 'parents',
                Child2: 'parents',
                Grandchild1: 'parents',
                DisconnectedGrandchild2: 'parents',
            },
        ),
    ])
    def test_depth_levels(self, monkeypatch, inheritance_instances, depth, expected_values):
        prop = get_queryable_property(Parent, 'plural')
        monkeypatch.setattr(prop, 'depth', depth)

        instances = Parent.objects.select_properties('plural').in_bulk([
            inheritance_instances[Parent].pk,
            inheritance_instances[Child1].pk,
            inheritance_instances[Child2].pk,
            inheritance_instances[Grandchild1].pk,
            inheritance_instances[DisconnectedGrandchild2].pk,
        ])
        for model, expected_value in expected_values.items():
            assert instances[inheritance_instances[model].pk].plural == expected_value
