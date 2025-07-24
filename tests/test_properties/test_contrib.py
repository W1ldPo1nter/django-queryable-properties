# -*- coding: utf-8 -*-
import pytest
import six
from django.contrib.contenttypes.models import ContentType

from queryable_properties.properties import ContentTypeProperty, QueryableProperty
from queryable_properties.utils import get_queryable_property
from queryable_properties.utils.internal import QueryPath
from ..marks import skip_if_no_subqueries
from ..inheritance.models import Child1, Child2, DisconnectedGrandchild2, Grandchild1, Parent


@skip_if_no_subqueries
class TestContentTypeProperty(object):

    @pytest.mark.parametrize('kwargs', [
        {},
        {'field_names': ('model',), 'depth': 2, 'cached': True},
        {'model': 'some.Model', 'queryset': None, 'depth': 0},
    ])
    def test_initializer(self, kwargs):
        prop = ContentTypeProperty(**kwargs)
        assert prop._subquery_model == 'contenttypes.ContentType'
        assert prop._inner_queryset == prop._get_inner_queryset
        assert prop._field_names == kwargs.get('field_names')
        assert prop.depth == kwargs.get('depth')
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)

    def test_get_value_for_model(self):
        assert ContentTypeProperty()._get_value_for_model(Parent) == 'inheritance.parent'

    def test_get_condition_for_model(self):
        from django.db.models import OuterRef
        from django.db.models.lookups import IsNull

        result = ContentTypeProperty()._get_condition_for_model(Grandchild1, QueryPath('child1__grandchild1'))
        assert isinstance(result, IsNull)
        assert isinstance(result.lhs, OuterRef)
        assert result.lhs.name == 'child1__grandchild1'
        assert result.rhs is False

    @pytest.mark.django_db
    @pytest.mark.parametrize('select, expected_query_count', [
        (True, 1),
        (False, 6),
    ])
    def test_content_type_determination(self, django_assert_num_queries, inheritance_instances,
                                        select, expected_query_count):
        content_types_by_pk = {
            instance.pk: ContentType.objects.get_for_model(Child2 if model is DisconnectedGrandchild2 else model)
            for model, instance in six.iteritems(inheritance_instances)
            if issubclass(model, Parent)
        }
        queryset = Parent.objects.all()
        if select:
            queryset = queryset.select_properties('content_type')

        with django_assert_num_queries(expected_query_count):
            for instance in queryset:
                assert instance.content_type == content_types_by_pk[instance.pk]

    @pytest.mark.django_db
    @pytest.mark.parametrize('depth, expected_model', [
        (None, Grandchild1),
        (2, Grandchild1),
        (1, Child1),
        (0, Parent),
    ])
    def test_depth_levels(self, monkeypatch, inheritance_instances, depth, expected_model):
        prop = get_queryable_property(Parent, 'content_type')
        monkeypatch.setattr(prop, 'depth', depth)

        instance = Parent.objects.select_properties('content_type').get(pk=inheritance_instances[Grandchild1].pk)
        assert instance.content_type == ContentType.objects.get_for_model(expected_model)
