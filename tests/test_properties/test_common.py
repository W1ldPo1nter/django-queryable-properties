# encoding: utf-8

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
