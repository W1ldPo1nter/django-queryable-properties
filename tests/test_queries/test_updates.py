# encoding: utf-8

import pytest

from django import VERSION as DJANGO_VERSION
from django.db import models

from ..app_management.models import VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


@pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
def test_simple_update(model):
    queryset = model.objects.filter(major_minor='2.0')
    pks = list(queryset.values_list('pk', flat=True))
    assert queryset.update(major_minor='42.42') == len(pks)
    for pk in pks:
        version = model.objects.get(pk=pk)  # Reload from DB
        assert version.major_minor == '42.42'


@pytest.mark.parametrize('model, update_kwargs', [
    (VersionWithClassBasedProperties, {'version': '1.3.37'}),
    (VersionWithDecoratorBasedProperties, {'version': '1.3.37'}),
    # Also test that setting the same field(s) via multiple queryable
    # properties works as long as they try to set the same values
    (VersionWithClassBasedProperties, {'version': '1.3.37', 'major_minor': '1.3'}),
    (VersionWithDecoratorBasedProperties, {'version': '1.3.37', 'major_minor': '1.3'}),
])
def test_update_based_on_other_property(model, update_kwargs):
    queryset = model.objects.filter(version='1.3.1')
    pks = list(queryset.values_list('pk', flat=True))
    assert queryset.update(**update_kwargs) == len(pks)
    for pk in pks:
        version = model.objects.get(pk=pk)  # Reload from DB
        assert version.version == update_kwargs['version']


@pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Conditional expressions didn't exist before Django 1.8")
@pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
def test_update_using_conditional_expression(model):
    assert model.objects.filter(major=1, changes__isnull=True).count() == 6
    model.objects.filter(major=1).update(changes=models.Case(
        models.When(version='1.2.3', then=models.Value('1.2.3 changes')),
        models.When(version='1.3.0', then=models.Value('1.3.0 changes')),
        default=models.Value('1.3.1 changes')
    ))
    for version in ('1.2.3', '1.3.0', '1.3.1'):
        assert model.objects.filter(major=1, version=version, changes='{} changes'.format(version)).count() == 2
