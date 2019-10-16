# encoding: utf-8

from datetime import date
from itertools import chain

import pytest

from django import VERSION as DJANGO_VERSION
from django.db.models import Q

from ..models import VersionWithClassBasedProperties

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class TestValueCheckProperty(object):

    @pytest.mark.parametrize('index, is_alpha, is_beta, is_stable, is_unstable', [
        (0, False, True, False, True),
        (1, False, False, True, False),
        (2, False, False, True, False),
        (3, True, False, False, True),
    ])
    def test_getter(self, versions, index, is_alpha, is_beta, is_stable, is_unstable):
        version = versions[index]
        assert version.is_alpha is is_alpha
        assert version.is_beta is is_beta
        assert version.is_stable is is_stable
        assert version.is_unstable is is_unstable

    @pytest.mark.parametrize('condition, expected_count, expected_versions', [
        (Q(is_alpha=True), 2, {'2.0.0'}),
        (Q(is_beta=True), 2, {'1.2.3'}),
        (Q(is_stable=True), 4, {'1.3.0', '1.3.1'}),
        (Q(is_unstable=True), 4, {'1.2.3', '2.0.0'}),
        (Q(is_alpha=True) | Q(is_beta=True), 4, {'1.2.3', '2.0.0'}),
        (Q(is_stable=False), 4, {'1.2.3', '2.0.0'}),
        (Q(is_alpha=False), 6, {'1.2.3', '1.3.0', '1.3.1'}),
    ])
    def test_filter(self, condition, expected_count, expected_versions):
        results = VersionWithClassBasedProperties.objects.filter(condition)
        assert len(results) == expected_count
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


class TestRangeCheckProperty(object):

    def test_final_value(self, monkeypatch):
        assert VersionWithClassBasedProperties.is_supported.final_value == date(2019, 1, 1)
        monkeypatch.setattr(VersionWithClassBasedProperties.is_supported, 'value', lambda: 5)
        assert VersionWithClassBasedProperties.is_supported.final_value == 5

    @pytest.mark.parametrize('index, value, include_boundaries, in_range, expected_result', [
        (3, date(2019, 1, 1), True, True, True),
        (0, date(2019, 1, 1), True, True, False),
        (3, date(2019, 1, 1), False, True, True),
        (3, date(2019, 1, 1), True, False, False),
        (0, date(2019, 1, 1), True, False, True),
        (3, date(2019, 1, 31), True, True, True),
        (3, date(2019, 1, 31), True, False, False),
        (3, date(2019, 1, 31), False, True, False),
        (3, date(2019, 1, 31), False, False, True),
        (3, date(2018, 11, 1), True, True, True),
        (3, date(2018, 11, 1), True, False, False),
        (3, date(2018, 11, 1), False, True, False),
        (3, date(2018, 11, 1), False, False, True),
    ])
    def test_getter(self, monkeypatch, versions, index, value, include_boundaries, in_range, expected_result):
        version = versions[index]
        monkeypatch.setattr(VersionWithClassBasedProperties.is_supported, 'value', value)
        monkeypatch.setattr(VersionWithClassBasedProperties.is_supported, 'include_boundaries', include_boundaries)
        monkeypatch.setattr(VersionWithClassBasedProperties.is_supported, 'in_range', in_range)
        assert version.is_supported == expected_result

    @pytest.mark.parametrize('value, include_boundaries, in_range, condition, should_contain_v2', [
        (date(2019, 1, 1), True, True, Q(is_supported=True), True),
        (date(2019, 1, 1), True, True, Q(is_supported=True, major=1), False),
        (date(2019, 1, 1), True, True, Q(is_supported=False), False),
        (date(2019, 1, 1), False, True, Q(is_supported=True), True),
        (date(2019, 1, 1), True, False, Q(is_supported=True), False),
        (date(2019, 1, 1), True, False, Q(is_supported=False), True),
        (date(2019, 1, 31), True, True, Q(is_supported=True), True),
        (date(2019, 1, 31), True, False, Q(is_supported=True), False),
        (date(2019, 1, 31), False, True, Q(is_supported=True), False),
        (date(2019, 1, 31), False, False, Q(is_supported=True), True),
        (date(2018, 11, 1), True, True, Q(is_supported=True), True),
        (date(2018, 11, 1), True, False, Q(is_supported=True), False),
        (date(2018, 11, 1), False, True, Q(is_supported=True), False),
        (date(2018, 11, 1), False, False, Q(is_supported=True), True),
    ])
    def test_filter(self, monkeypatch, value, include_boundaries, in_range, condition, should_contain_v2):
        monkeypatch.setattr(VersionWithClassBasedProperties.is_supported, 'value', value)
        monkeypatch.setattr(VersionWithClassBasedProperties.is_supported, 'include_boundaries', include_boundaries)
        monkeypatch.setattr(VersionWithClassBasedProperties.is_supported, 'in_range', in_range)
        assert VersionWithClassBasedProperties.objects.filter(condition, version='2.0.0').exists() is should_contain_v2

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    def test_annotation(self):
        results = VersionWithClassBasedProperties.objects.order_by('-is_supported', 'version')
        assert list(results.select_properties('version').values_list('version', flat=True)) == [
            '2.0.0', '2.0.0', '1.2.3', '1.2.3', '1.3.0', '1.3.0', '1.3.1', '1.3.1'
        ]
