# -*- coding: utf-8 -*-

import pytest

from ..app_management.models import (
    ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties, VersionWithClassBasedProperties,
    VersionWithDecoratorBasedProperties,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True), pytest.mark.usefixtures('versions')]


@pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
async def test_aiterator(model):
    queryset = model.objects.filter(version_count=4).select_properties('version_count')
    async for application in queryset.aiterator():
        assert model.version_count.has_cached_value(application)
        assert application.version_count == 4
    assert queryset._result_cache is None


@pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
async def test_aupdate(model):
    queryset = model.objects.filter(major_minor='2.0')
    pks = [pk async for pk in queryset.values_list('pk', flat=True)]
    assert await queryset.aupdate(major_minor='42.42') == len(pks)
    for pk in pks:
        version = await model.objects.aget(pk=pk)  # Reload from DB
        assert version.major_minor == '42.42'
