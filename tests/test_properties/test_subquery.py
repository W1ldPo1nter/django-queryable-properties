# -*- coding: utf-8 -*-
import pytest
from django import VERSION as DJANGO_VERSION
from django.db import models

from queryable_properties.properties import QueryableProperty, SubqueryExistenceCheckProperty, SubqueryFieldProperty
from queryable_properties.utils import get_queryable_property
from ..app_management.models import (
    ApplicationWithClassBasedProperties, CategoryWithClassBasedProperties, VersionWithClassBasedProperties,
)

pytestmark = [
    pytest.mark.skipif(DJANGO_VERSION < (1, 11), reason="Explicit subqueries didn't exist before Django 1.11")
]


class TestSubqueryFieldProperty(object):

    @pytest.mark.parametrize('kwargs', [
        {
            'queryset': ApplicationWithClassBasedProperties.objects.filter(name='test'),
            'field_name': 'name',
        },
        {
            'queryset': ApplicationWithClassBasedProperties.objects.all(),
            'field_name': 'common_data',
            'output_field': models.IntegerField(),
            'cached': True,
        }
    ])
    def test_initializer(self, kwargs):
        prop = SubqueryFieldProperty(**kwargs)
        assert prop.queryset is kwargs['queryset']
        assert prop.field_name == kwargs['field_name']
        assert prop.output_field is kwargs.get('output_field')
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('field_name, expected_value', [
        ('version', '2.0.0'),
        ('major', 2),
    ])
    def test_build_subquery(self, monkeypatch, applications, field_name, expected_value):
        prop = get_queryable_property(ApplicationWithClassBasedProperties, 'highest_version')
        monkeypatch.setattr(prop, 'field_name', field_name)
        assert applications[0].highest_version == expected_value


class TestSubqueryExistenceCheckProperty(object):

    @pytest.mark.parametrize('kwargs', [
        {
            'queryset': ApplicationWithClassBasedProperties.objects.filter(name='test'),
        },
        {
            'queryset': ApplicationWithClassBasedProperties.objects.all(),
            'negated': True,
            'cached': True,
        }
    ])
    def test_initializer(self, kwargs):
        prop = SubqueryExistenceCheckProperty(**kwargs)
        assert prop.queryset is kwargs['queryset']
        assert prop.negated == kwargs.get('negated', False)
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('negated, delete_v2, expected_result', [
        (False, False, True),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ])
    def test_build_subquery(self, monkeypatch, categories, negated, delete_v2, expected_result):
        if delete_v2:
            VersionWithClassBasedProperties.objects.filter(major=2).delete()
        prop = get_queryable_property(CategoryWithClassBasedProperties, 'has_v2')
        monkeypatch.setattr(prop, 'negated', negated)
        assert categories[0].has_v2 is expected_result
