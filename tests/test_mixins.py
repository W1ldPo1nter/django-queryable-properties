# encoding: utf-8
"""Tests for basic features of the Query and QuerySet mixins."""

import pytest

from django.utils.six.moves import cPickle

from .models import VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties


@pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
def test_query_attributes(model):
    queryset = model.objects.all()
    # Also test the initializer of the QueryMixin by creating a new instance
    queries = (queryset.query, queryset.query.__class__(queryset.model))
    for query in queries:
        assert query._queryable_property_annotations == {}
        assert query._required_annotation_stack == []


@pytest.mark.django_db
@pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
def test_pickle_unpickle(versions, model):
    queryset1 = model.objects.filter(major_minor='1.3').order_by('-version').select_properties('version')
    expected_versions = list(queryset1)
    serialized_query = cPickle.dumps(queryset1.query)
    queryset2 = model.objects.all()
    queryset2.query = cPickle.loads(serialized_query)
    serialized_queryset = cPickle.dumps(queryset1)
    queryset3 = cPickle.loads(serialized_queryset)
    for queryset in (queryset1, queryset2, queryset3):
        versions = list(queryset)
        assert versions == expected_versions
        assert all(model.version._has_cached_value(obj) for obj in queryset)
