# -*- coding: utf-8 -*-
import pytest
import six
from django import VERSION as DJANGO_VERSION
from django.db.models import Avg, Q

from queryable_properties.properties import AggregateProperty, AnnotationProperty, RelatedExistenceCheckProperty
from queryable_properties.utils import get_queryable_property
from queryable_properties.utils.internal import QueryPath
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

    @pytest.mark.parametrize('path, kwargs, expected_query_path', [
        ('my_field', {}, QueryPath('my_field__isnull')),
        ('my_relation__my_field', {'negated': True}, QueryPath('my_relation__my_field__isnull')),
        ('my_field', {'cached': True}, QueryPath('my_field__isnull')),
    ])
    def test_initializer(self, path, kwargs, expected_query_path):
        prop = RelatedExistenceCheckProperty(path, **kwargs)
        assert prop.query_path == expected_query_path
        assert prop.negated is kwargs.get('negated', False)
        assert prop.cached is kwargs.get('cached', RelatedExistenceCheckProperty.cached)

    @pytest.mark.parametrize('path', ['my_field', 'my_relation__my_field'])
    def test_base_condition(self, path):
        prop = RelatedExistenceCheckProperty(path)
        condition = prop._base_condition
        assert isinstance(condition, Q)
        assert len(condition.children) == 1
        assert condition.children[0] == (six.text_type(QueryPath(path) + 'isnull'), False)

    @pytest.mark.parametrize('negated', [False, True])
    def test_getter(self, monkeypatch, categories, applications, negated):
        monkeypatch.setattr(get_queryable_property(CategoryWithClassBasedProperties, 'has_versions'),
                            'negated', negated)
        assert categories[0].has_versions is not negated
        assert categories[1].has_versions is not negated
        applications[1].versions.all().delete()
        assert categories[0].has_versions is not negated
        assert categories[1].has_versions is negated

    @pytest.mark.parametrize('negated', [False, True])
    def test_getter_based_on_non_relation_field(self, monkeypatch, applications, negated):
        monkeypatch.setattr(get_queryable_property(ApplicationWithClassBasedProperties, 'has_version_with_changelog'),
                            'negated', negated)
        assert applications[0].has_version_with_changelog is not negated
        assert applications[1].has_version_with_changelog is not negated
        applications[0].versions.filter(major=2).delete()
        assert applications[0].has_version_with_changelog is negated
        assert applications[1].has_version_with_changelog is not negated

    @pytest.mark.parametrize('negated', [False, True])
    def test_filter(self, monkeypatch, categories, applications, negated):
        monkeypatch.setattr(get_queryable_property(CategoryWithClassBasedProperties, 'has_versions'),
                            'negated', negated)
        queryset = CategoryWithClassBasedProperties.objects.all()
        assert set(queryset.filter(has_versions=not negated)) == set(categories[:2])
        assert not queryset.filter(has_versions=negated).exists()
        applications[1].versions.all().delete()
        assert queryset.get(has_versions=not negated) == categories[0]
        assert queryset.get(has_versions=negated) == categories[1]

    @pytest.mark.parametrize('negated', [False, True])
    def test_filter_based_on_non_relation_field(self, monkeypatch, categories, applications, negated):
        monkeypatch.setattr(get_queryable_property(ApplicationWithClassBasedProperties, 'has_version_with_changelog'),
                            'negated', negated)
        app_queryset = ApplicationWithClassBasedProperties.objects.all()
        category_queryset = CategoryWithClassBasedProperties.objects.all()
        assert set(app_queryset.filter(has_version_with_changelog=not negated)) == set(applications[:2])
        assert not app_queryset.filter(has_version_with_changelog=negated).exists()
        assert (set(category_queryset.filter(applications__has_version_with_changelog=not negated)) ==
                set(categories[:2]))
        assert not category_queryset.filter(applications__has_version_with_changelog=negated).exists()
        applications[1].versions.filter(major=2).delete()
        assert app_queryset.get(has_version_with_changelog=not negated) == applications[0]
        assert app_queryset.get(has_version_with_changelog=negated) == applications[1]
        assert category_queryset.get(applications__has_version_with_changelog=not negated) == categories[0]
        assert category_queryset.get(applications__has_version_with_changelog=negated) == categories[1]

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
