# encoding: utf-8

from contextlib import contextmanager
from datetime import date
from itertools import chain

import pytest

from django import VERSION as DJANGO_VERSION
from django.db.models import Avg, Q
from django.utils.translation import trans_real

from queryable_properties.compat import nullcontext
from queryable_properties.properties import AggregateProperty, AnnotationProperty, RelatedExistenceCheckProperty
from ..app_management.models import (ApplicationWithClassBasedProperties, CategoryWithClassBasedProperties,
                                     VersionWithClassBasedProperties)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class TestValueCheckProperty(object):

    @pytest.mark.parametrize('index, is_alpha, is_beta, is_stable, is_unstable, released_in_2018', [
        (0, False, True, False, True, False),
        (1, False, False, True, False, False),
        (2, False, False, True, False, True),
        (3, True, False, False, True, True),
    ])
    def test_getter(self, versions, index, is_alpha, is_beta, is_stable, is_unstable, released_in_2018):
        version = versions[index]
        assert version.is_alpha is is_alpha
        assert version.is_beta is is_beta
        assert version.is_stable is is_stable
        assert version.is_unstable is is_unstable
        assert version.shares_common_data is True
        assert version.released_in_2018 is released_in_2018

    @pytest.mark.parametrize('condition, expected_versions', [
        (Q(is_alpha=True), {'2.0.0'}),
        (Q(is_beta=True), {'1.2.3'}),
        (Q(is_stable=True), {'1.3.0', '1.3.1'}),
        (Q(is_unstable=True), {'1.2.3', '2.0.0'}),
        (Q(is_alpha=True) | Q(is_beta=True), {'1.2.3', '2.0.0'}),
        (Q(is_stable=False), {'1.2.3', '2.0.0'}),
        (Q(is_alpha=False), {'1.2.3', '1.3.0', '1.3.1'}),
        (Q(shares_common_data=False), set()),
    ])
    def test_filter(self, condition, expected_versions):
        results = VersionWithClassBasedProperties.objects.filter(condition)
        assert len(results) == len(expected_versions) * 2
        assert set(result.version for result in results) == expected_versions

    @pytest.mark.skipif(DJANGO_VERSION < (1, 9), reason="Transforms and lookup couldn't be combined before Django 1.9")
    @pytest.mark.parametrize('condition, expected_versions', [
        (Q(released_in_2018=True), {'1.3.1', '2.0.0'}),
        (Q(released_in_2018=True, is_alpha=True), {'2.0.0'}),
        (Q(released_in_2018=False), {'1.2.3', '1.3.0'}),
    ])
    def test_filter_based_on_transform(self, condition, expected_versions):
        results = VersionWithClassBasedProperties.objects.filter(condition)
        assert len(results) == len(expected_versions) * 2
        assert set(result.version for result in results) == expected_versions

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    @pytest.mark.parametrize('ordering, expected_version_order', [
        (('-is_stable', '-version'), ['1.3.1', '1.3.0', '2.0.0', '1.2.3']),
        (('-is_unstable', '-is_alpha', 'version'), ['2.0.0', '1.2.3', '1.3.0', '1.3.1']),
    ])
    def test_annotation(self, ordering, expected_version_order):
        results = VersionWithClassBasedProperties.objects.order_by(*ordering)
        # There are 2 objects for each version number.
        expected_version_order = list(chain(*zip(expected_version_order, expected_version_order)))
        assert [result.version for result in results] == expected_version_order

    @pytest.mark.skipif(DJANGO_VERSION < (1, 9), reason="Transforms and lookup couldn't be combined before Django 1.9")
    def test_annotation_based_on_transform(self):
        results = VersionWithClassBasedProperties.objects.order_by('released_in_2018', '-version')
        assert [result.version for result in results] == [
            '1.3.0', '1.3.0', '1.2.3', '1.2.3', '2.0.0', '2.0.0', '1.3.1', '1.3.1'
        ]


class TestRangeCheckProperty(object):

    def test_final_value(self, monkeypatch):
        assert VersionWithClassBasedProperties.is_supported.final_value == date(2019, 1, 1)
        monkeypatch.setattr(VersionWithClassBasedProperties.is_supported, 'value', lambda: 5)
        assert VersionWithClassBasedProperties.is_supported.final_value == 5

    @pytest.mark.parametrize(
        'index, prop_name, value, include_boundaries, include_missing, in_range, expected_result',
        [
            (3, 'is_supported', date(2019, 1, 1), True, True, True, True),
            (3, 'is_supported', date(2019, 1, 1), True, True, False, False),
            (3, 'is_supported', date(2019, 1, 1), True, False, True, False),
            (0, 'supported_in_2018', 2018, True, True, True, False),
            (3, 'supported_in_2018', 2018, False, True, True, False),
            (0, 'supported_in_2018', 2018, True, True, False, True),
            (3, 'supported_in_2018', 2018, True, False, False, True),
            (0, 'is_supported', date(2016, 12, 31), True, True, True, True),
            (0, 'is_supported', date(2016, 12, 31), True, True, False, False),
            (0, 'is_supported', date(2016, 12, 31), False, True, True, False),
            (0, 'is_supported', date(2016, 12, 31), False, True, False, True),
            (3, 'is_supported', date(2018, 11, 1), True, True, True, True),
            (3, 'is_supported', date(2018, 11, 1), True, True, False, False),
            (3, 'is_supported', date(2018, 11, 1), False, True, True, False),
            (3, 'is_supported', date(2018, 11, 1), False, True, False, True),
        ]
    )
    def test_getter(self, monkeypatch, versions, index, prop_name, value, include_boundaries, include_missing,
                    in_range, expected_result):
        version = versions[index]
        prop = getattr(VersionWithClassBasedProperties, prop_name)
        monkeypatch.setattr(prop, 'value', value)
        monkeypatch.setattr(prop, 'include_boundaries', include_boundaries)
        monkeypatch.setattr(prop, 'include_missing', include_missing)
        monkeypatch.setattr(prop, 'in_range', in_range)
        assert getattr(version, prop_name) is expected_result

    @pytest.mark.parametrize('value, include_boundaries, include_missing, in_range, condition, expected_versions', [
        (date(2019, 1, 1), True, True, True, Q(is_supported=True), {'2.0.0'}),
        (date(2019, 1, 1), True, True, True, Q(is_supported=True, major=1), set()),
        (date(2019, 1, 1), False, True, True, Q(is_supported=True), {'2.0.0'}),
        (date(2019, 1, 1), True, True, True, Q(is_supported=False), {'1.2.3', '1.3.0', '1.3.1'}),
        (date(2019, 1, 1), True, True, False, Q(is_supported=True), {'1.2.3', '1.3.0', '1.3.1'}),
        (date(2019, 1, 1), True, True, False, Q(is_supported=False), {'2.0.0'}),
        (date(2019, 1, 1), True, False, True, Q(is_supported=True), set()),
        (date(2019, 1, 1), True, False, False, Q(is_supported=True), {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (date(2016, 12, 31), True, True, True, Q(is_supported=True), {'1.2.3'}),
        (date(2016, 12, 31), True, True, False, Q(is_supported=True), {'1.3.0', '1.3.1', '2.0.0'}),
        (date(2016, 12, 31), False, True, True, Q(is_supported=True), set()),
        (date(2016, 12, 31), False, True, False, Q(is_supported=True), {'1.2.3', '1.3.0', '1.3.1', '2.0.0'}),
        (date(2018, 11, 1), True, True, True, Q(is_supported=True), {'1.3.1', '2.0.0'}),
        (date(2018, 11, 1), True, True, False, Q(is_supported=True), {'1.2.3', '1.3.0'}),
        (date(2018, 11, 1), False, True, True, Q(is_supported=True), {'1.3.1'}),
        (date(2018, 11, 1), False, True, False, Q(is_supported=True), {'1.2.3', '1.3.0', '2.0.0'}),
    ])
    def test_filter(self, monkeypatch, value, include_boundaries, include_missing, in_range, condition,
                    expected_versions):
        prop = VersionWithClassBasedProperties.is_supported
        monkeypatch.setattr(prop, 'value', value)
        monkeypatch.setattr(prop, 'include_boundaries', include_boundaries)
        monkeypatch.setattr(prop, 'include_missing', include_missing)
        monkeypatch.setattr(prop, 'in_range', in_range)
        results = VersionWithClassBasedProperties.objects.filter(condition)
        assert set(version.version for version in results) == expected_versions

    @pytest.mark.skipif(DJANGO_VERSION < (1, 9), reason="Transforms and lookup couldn't be combined before Django 1.9")
    @pytest.mark.parametrize('include_boundaries, include_missing, in_range, condition, expected_versions', [
        (True, True, True, Q(supported_in_2018=True), {'1.3.1', '2.0.0'}),
        (True, True, True, Q(supported_in_2018=True, major=1), {'1.3.1'}),
        (True, True, True, Q(supported_in_2018=False), {'1.2.3', '1.3.0'}),
        (True, False, True, Q(supported_in_2018=True), {'1.3.1'}),
        (False, True, True, Q(supported_in_2018=True), set()),
        (True, True, False, Q(supported_in_2018=True), {'1.2.3', '1.3.0'}),
        (True, True, False, Q(supported_in_2018=False), {'1.3.1', '2.0.0'}),
        (True, False, False, Q(supported_in_2018=True), {'1.2.3', '1.3.0', '2.0.0'}),
    ])
    def test_filter_based_on_transform(self, monkeypatch, include_boundaries, include_missing, in_range, condition,
                                       expected_versions):
        prop = VersionWithClassBasedProperties.supported_in_2018
        monkeypatch.setattr(prop, 'include_boundaries', include_boundaries)
        monkeypatch.setattr(prop, 'include_missing', include_missing)
        monkeypatch.setattr(prop, 'in_range', in_range)
        results = VersionWithClassBasedProperties.objects.filter(condition)
        assert set(version.version for version in results) == expected_versions

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    def test_annotation(self):
        results = VersionWithClassBasedProperties.objects.order_by('-is_supported', 'version')
        assert list(results.select_properties('version').values_list('version', flat=True)) == [
            '2.0.0', '2.0.0', '1.2.3', '1.2.3', '1.3.0', '1.3.0', '1.3.1', '1.3.1'
        ]

    @pytest.mark.skipif(DJANGO_VERSION < (1, 9), reason="Transforms and lookup couldn't be combined before Django 1.9")
    def test_annotation_based_on_transform(self):
        results = VersionWithClassBasedProperties.objects.order_by('-supported_in_2018', 'version')
        assert list(results.select_properties('version').values_list('version', flat=True)) == [
            '1.3.1', '1.3.1', '2.0.0', '2.0.0', '1.2.3', '1.2.3', '1.3.0', '1.3.0'
        ]


class TestRelatedExistenceCheckProperty(object):

    @pytest.mark.parametrize('path, cached, expected_filter, expected_cached', [
        ('my_field', False, 'my_field__isnull', False),
        ('my_relation__my_field', None, 'my_relation__my_field__isnull', False),
        ('my_field', True, 'my_field__isnull', True),
    ])
    def test_initializer(self, path, cached, expected_filter, expected_cached):
        prop = RelatedExistenceCheckProperty(path, cached=cached)
        assert prop.filters == {expected_filter: False}
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


class TestMappingProperty(object):

    TRANSLATION_TERMS = ('Alpha', 'Beta', 'Stable')

    @contextmanager
    def apply_dummy_translations(self):
        catalog_dict = trans_real.catalog()._catalog
        if hasattr(catalog_dict, '_catalogs'):
            catalog_dict = catalog_dict._catalogs[0]
        for term in self.TRANSLATION_TERMS:
            catalog_dict[term] = term[1:]
        yield
        for term in self.TRANSLATION_TERMS:
            del catalog_dict[term]

    @pytest.mark.parametrize('apply_dummy_translations, expected_verbose_names', [
        (False, ['Beta', 'Stable', 'Stable', 'Alpha']),
        (True, ['eta', 'table', 'table', 'lpha']),
    ])
    def test_getter(self, versions, apply_dummy_translations, expected_verbose_names):
        with self.apply_dummy_translations() if apply_dummy_translations else nullcontext():
            for i, expected_verbose_name in enumerate(expected_verbose_names):
                assert str(versions[i].release_type_verbose_name) == expected_verbose_name

    @pytest.mark.parametrize('apply_dummy_translations', [False, True])
    def test_getter_default(self, versions, apply_dummy_translations):
        versions[0].release_type = 'x'
        with self.apply_dummy_translations() if apply_dummy_translations else nullcontext():
            assert versions[0].release_type_verbose_name is None

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    @pytest.mark.parametrize('apply_dummy_translations, filter_value, expected_count', [
        (False, 'Alpha', 2),
        (False, 'Stable', 4),
        (True, 'eta', 2),
        (True, 'table', 4),
    ])
    def test_filter(self, apply_dummy_translations, filter_value, expected_count):
        with self.apply_dummy_translations() if apply_dummy_translations else nullcontext():
            queryset = VersionWithClassBasedProperties.objects.filter(release_type_verbose_name=filter_value)
            assert queryset.count() == expected_count

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    @pytest.mark.parametrize('apply_dummy_translations', [False, True])
    def test_filter_default(self, versions, apply_dummy_translations):
        versions[0].release_type = 'x'
        versions[0].save()
        with self.apply_dummy_translations() if apply_dummy_translations else nullcontext():
            assert VersionWithClassBasedProperties.objects.get(release_type_verbose_name=None) == versions[0]

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    @pytest.mark.parametrize('apply_dummy_translations, expected_verbose_names', [
        (False, ['Beta', 'Stable', 'Stable', 'Alpha']),
        (True, ['eta', 'table', 'table', 'lpha']),
    ])
    def test_annotation(self, applications, apply_dummy_translations, expected_verbose_names):
        with self.apply_dummy_translations() if apply_dummy_translations else nullcontext():
            queryset = VersionWithClassBasedProperties.objects.order_by('major', 'minor', 'patch')
            queryset = queryset.filter(application=applications[0]).select_properties('release_type_verbose_name')
            assert list(queryset.values_list('release_type_verbose_name', flat=True)) == expected_verbose_names

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    @pytest.mark.parametrize('apply_dummy_translations', [False, True])
    def test_annotation_default(self, versions, apply_dummy_translations):
        versions[0].release_type = 'x'
        versions[0].save()
        with self.apply_dummy_translations() if apply_dummy_translations else nullcontext():
            queryset = VersionWithClassBasedProperties.objects.select_properties('release_type_verbose_name')
            assert queryset.values_list('release_type_verbose_name', flat=True).get(pk=versions[0].pk) is None


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
