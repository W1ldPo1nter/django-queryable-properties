# encoding: utf-8
"""Tests for basic features of the Query and QuerySet mixins."""

import pytest

from django.utils.six.moves import cPickle

from .models import ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties


@pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
def test_query_attributes(model):
    queryset = model.objects.all()
    # Also test the initializer of the QueryMixin by creating a new instance
    queries = (queryset.query, queryset.query.__class__(queryset.model))
    for query in queries:
        assert query._queryable_property_annotations == {}
        assert query._required_annotation_stack == []


@pytest.mark.django_db
@pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
def test_pickle_unpickle(versions, model):
    queryset1 = model.objects.filter(version_count=4).order_by('name').select_properties('version_count')
    expected_applications = list(queryset1)
    serialized_query = cPickle.dumps(queryset1.query)
    queryset2 = model.objects.all()
    queryset2.query = cPickle.loads(serialized_query)
    serialized_queryset = cPickle.dumps(queryset1)
    queryset3 = cPickle.loads(serialized_queryset)
    for queryset in (queryset1, queryset2, queryset3):
        versions = list(queryset)
        assert versions == expected_applications
        assert all(model.version_count._has_cached_value(obj) for obj in queryset)
