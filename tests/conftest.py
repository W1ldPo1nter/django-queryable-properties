# encoding: utf-8

import pytest

from .models import ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties


@pytest.fixture
def applications():
    return [
        ApplicationWithClassBasedProperties.objects.create(name='My cool App'),
        ApplicationWithClassBasedProperties.objects.create(name='Another App'),
        ApplicationWithDecoratorBasedProperties.objects.create(name='My cool App'),
        ApplicationWithDecoratorBasedProperties.objects.create(name='Another App'),
    ]


@pytest.fixture
def versions(applications):
    objs = []
    for application in applications:
        objs.extend([
            application.versions.create(major=1, minor=2, patch=3),
            application.versions.create(major=1, minor=3, patch=0),
            application.versions.create(major=1, minor=3, patch=1),
            application.versions.create(major=2, minor=0, patch=0),
        ])
    return objs
