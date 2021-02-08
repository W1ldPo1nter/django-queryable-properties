# encoding: utf-8

from datetime import date

import pytest
from mock import Mock

try:
    from django.db.models import Value
except ImportError:
    Value = Mock()
try:
    from django.db.models.functions import Concat
except ImportError:
    Concat = Mock(return_value=Mock(output_field=None))

from .app_management.models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                                    CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties)
from .dummy_lib.models import ReleaseTypeModel


@pytest.fixture
def categories():
    return [
        CategoryWithClassBasedProperties.objects.create(name='Linux apps'),
        CategoryWithClassBasedProperties.objects.create(name='Windows apps'),
        CategoryWithDecoratorBasedProperties.objects.create(name='Linux apps'),
        CategoryWithDecoratorBasedProperties.objects.create(name='Windows apps'),
    ]


@pytest.fixture
def applications(categories):
    apps = [
        ApplicationWithClassBasedProperties.objects.create(name='My cool App'),
        ApplicationWithClassBasedProperties.objects.create(name='Another App'),
        ApplicationWithDecoratorBasedProperties.objects.create(name='My cool App'),
        ApplicationWithDecoratorBasedProperties.objects.create(name='Another App'),
    ]
    apps[0].categories.add(categories[0])
    apps[1].categories.add(categories[0])
    apps[1].categories.add(categories[1])
    apps[2].categories.add(categories[2])
    apps[3].categories.add(categories[2])
    apps[3].categories.add(categories[3])
    return apps


@pytest.fixture
def versions(applications):
    objs = []
    for application in applications:
        objs.extend([
            application.versions.create(major=1, minor=2, patch=3, release_type=ReleaseTypeModel.BETA,
                                        supported_until=date(2016, 12, 31)),
            application.versions.create(major=1, minor=3, patch=0,
                                        supported_from=date(2017, 1, 1), supported_until=date(2017, 12, 31)),
            application.versions.create(major=1, minor=3, patch=1,
                                        supported_from=date(2018, 1, 1), supported_until=date(2018, 12, 31)),
            application.versions.create(major=2, minor=0, patch=0, changes='Amazing new features',
                                        release_type=ReleaseTypeModel.ALPHA, supported_from=date(2018, 11, 1)),
        ])
    return objs
