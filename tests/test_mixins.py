# encoding: utf-8
"""Tests for basic features of the Query and QuerySet mixins."""

import pytest

from six.moves import cPickle

from .models import ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties


@pytest.mark.django_db
@pytest.mark.usefixtures('versions')
@pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
def test_pickle_unpickle(model):
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
