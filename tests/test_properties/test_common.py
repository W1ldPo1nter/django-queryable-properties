# encoding: utf-8

from datetime import date
from itertools import chain

import pytest

from django import VERSION as DJANGO_VERSION
from django.db.models import Q

from ..app_management.models import ApplicationWithClassBasedProperties, VersionWithClassBasedProperties

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


class TestAggregateProperty(object):

    def test_getter(self, applications, versions):
        assert applications[0].major_sum == 5
        versions[0].delete()
        assert applications[0].major_sum == 4

    def test_annotation(self, applications, versions):
        versions[0].delete()
        assert list(ApplicationWithClassBasedProperties.objects.order_by('-major_sum')) == [
            applications[1], applications[0]
        ]
