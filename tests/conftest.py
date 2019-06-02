# encoding: utf-8

import pytest

from .models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                     CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties)


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
            application.versions.create(major=1, minor=2, patch=3),
            application.versions.create(major=1, minor=3, patch=0),
            application.versions.create(major=1, minor=3, patch=1),
            application.versions.create(major=2, minor=0, patch=0, changes='Amazing new features'),
        ])
    return objs
