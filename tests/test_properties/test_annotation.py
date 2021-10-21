# -*- coding: utf-8 -*-
import pytest

from django import VERSION as DJANGO_VERSION
from django.db.models import Avg, Q

from queryable_properties.properties import AggregateProperty, AnnotationProperty, RelatedExistenceCheckProperty
from ..app_management.models import ApplicationWithClassBasedProperties, CategoryWithClassBasedProperties

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class TestAnnotationProperty(object):

    @pytest.mark.parametrize('cached, expected_cached', [
        (None, False),
        (False, False),
        (True, True),
    ])
    def test_initializer(self, cached, expected_cached):
        annotation = Avg('test')
        prop = AnnotationProperty(annotation, cached=cached)
        assert prop.annotation is annotation
        assert prop.cached is expected_cached

    def test_getter(self, categories):
        assert categories[0].version_count == 8
        assert categories[1].version_count == 4

    def test_annotation(self, categories):
        assert list(CategoryWithClassBasedProperties.objects.order_by('-version_count')) == [
            categories[0], categories[1]
        ]


class TestAggregateProperty(object):

    @pytest.mark.parametrize('cached, expected_cached', [
        (None, False),
        (False, False),
        (True, True),
    ])
    def test_initializer(self, cached, expected_cached):
        annotation = Avg('test')
        prop = AggregateProperty(annotation, cached=cached)
        assert prop.annotation is annotation
        assert prop.cached is expected_cached

    def test_getter(self, applications, versions):
        assert applications[0].major_sum == 5
        versions[0].delete()
        assert applications[0].major_sum == 4


class TestRelatedExistenceCheckProperty(object):

    @pytest.mark.parametrize('path, cached, expected_filter, expected_cached', [
        ('my_field', False, 'my_field__isnull', False),
        ('my_relation__my_field', None, 'my_relation__my_field__isnull', False),
        ('my_field', True, 'my_field__isnull', True),
    ])
    def test_initializer(self, path, cached, expected_filter, expected_cached):
        prop = RelatedExistenceCheckProperty(path, cached=cached)
        assert isinstance(prop.filter, Q)
        assert len(prop.filter.children) == 1
        assert prop.filter.children[0] == (expected_filter, False)
        assert prop.cached is expected_cached

    def test_getter(self, categories, applications):
        assert categories[0].has_versions is True
        assert categories[1].has_versions is True
        applications[1].versions.all().delete()
        assert categories[0].has_versions is True
        assert categories[1].has_versions is False

    def test_getter_based_on_non_relation_field(self, applications):
        assert applications[0].has_version_with_changelog is True
        assert applications[1].has_version_with_changelog is True
        applications[0].versions.filter(major=2).delete()
        assert applications[0].has_version_with_changelog is False
        assert applications[1].has_version_with_changelog is True

    def test_filter(self, categories, applications):
        queryset = CategoryWithClassBasedProperties.objects.all()
        assert set(queryset.filter(has_versions=True)) == set(categories[:2])
        assert not queryset.filter(has_versions=False).exists()
        applications[1].versions.all().delete()
        assert queryset.get(has_versions=True) == categories[0]
        assert queryset.get(has_versions=False) == categories[1]

    def test_filter_based_on_non_relation_field(self, categories, applications):
        app_queryset = ApplicationWithClassBasedProperties.objects.all()
        category_queryset = CategoryWithClassBasedProperties.objects.all()
        assert set(app_queryset.filter(has_version_with_changelog=True)) == set(applications[:2])
        assert not app_queryset.filter(has_version_with_changelog=False).exists()
        assert set(category_queryset.filter(applications__has_version_with_changelog=True)) == set(categories[:2])
        assert not category_queryset.filter(applications__has_version_with_changelog=False).exists()
        applications[1].versions.filter(major=2).delete()
        assert app_queryset.get(has_version_with_changelog=True) == applications[0]
        assert app_queryset.get(has_version_with_changelog=False) == applications[1]
        assert category_queryset.get(applications__has_version_with_changelog=True) == categories[0]
        assert category_queryset.get(applications__has_version_with_changelog=False) == categories[1]

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    def test_annotation(self, categories, applications):
        queryset = CategoryWithClassBasedProperties.objects.all()
        assert list(queryset.order_by('has_versions', 'pk')) == categories[:2]
        applications[1].versions.all().delete()
        assert list(queryset.order_by('has_versions', 'pk')) == [categories[1], categories[0]]

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    def test_annotation_based_on_non_relation_field(self, categories, applications):
        app_queryset = ApplicationWithClassBasedProperties.objects.all()
        category_queryset = CategoryWithClassBasedProperties.objects.all()
        assert list(app_queryset.order_by('-has_version_with_changelog', '-pk')) == [applications[1], applications[0]]
        assert list(category_queryset.order_by('-applications__has_version_with_changelog', '-pk')) == [
            categories[1], categories[0], categories[0]]
        applications[1].versions.filter(major=2).delete()
        assert list(app_queryset.order_by('-has_version_with_changelog', '-pk')) == applications[:2]
        assert list(category_queryset.order_by('-applications__has_version_with_changelog', '-pk')) == [
            categories[0], categories[1], categories[0]]
