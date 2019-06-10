# encoding: utf-8

import pytest

from django import VERSION as DJANGO_VERSION

from ..conftest import Concat, Value
from ..models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                      VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class TestAggregateAnnotations(object):

    @pytest.mark.parametrize('model, order_by, reverse, with_selection', [
        (ApplicationWithClassBasedProperties, 'version_count', False, False),
        (ApplicationWithDecoratorBasedProperties, 'version_count', False, False),
        (ApplicationWithClassBasedProperties, 'version_count', False, True),
        (ApplicationWithDecoratorBasedProperties, 'version_count', False, True),
        (ApplicationWithClassBasedProperties, '-version_count', True, False),
        (ApplicationWithDecoratorBasedProperties, '-version_count', True, False),
        (ApplicationWithClassBasedProperties, '-version_count', True, True),
        (ApplicationWithDecoratorBasedProperties, '-version_count', True, True),
    ])
    def test_single_model(self, model, order_by, reverse, with_selection):
        model.objects.all()[0].versions.all()[0].delete()
        queryset = model.objects.all()
        if with_selection:
            queryset = queryset.select_properties('version_count')
        results = list(queryset.order_by(order_by))
        assert results == sorted(results, key=lambda application: application.version_count, reverse=reverse)
        # Check that ordering by a property annotation does not lead to a
        # selection of the property annotation
        assert all(model.version_count._has_cached_value(application) is with_selection for application in results)

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_across_relation(self, model):
        model.objects.all()[0].delete()  # Create a different version count for the application fixtures
        results = list(model.objects.order_by('application__version_count'))
        assert results == sorted(results, key=lambda version: version.application.version_count)


@pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
class TestExpressionAnnotations(object):

    @pytest.mark.parametrize('model, order_by, reverse, with_selection', [
        # All parametrizations are expected to yield results ordered by the
        # full version (ASC/DESC depending on the reverse parameter).
        (VersionWithClassBasedProperties, 'version', False, False),
        (VersionWithDecoratorBasedProperties, 'version', False, False),
        (VersionWithClassBasedProperties, 'version', False, True),
        (VersionWithDecoratorBasedProperties, 'version', False, True),
        (VersionWithClassBasedProperties, '-version', True, False),
        (VersionWithDecoratorBasedProperties, '-version', True, False),
        (VersionWithClassBasedProperties, '-version', True, True),
        (VersionWithDecoratorBasedProperties, '-version', True, True),
        (VersionWithClassBasedProperties, Concat(Value('V'), 'version').asc(), False, False),
        (VersionWithDecoratorBasedProperties, Concat(Value('V'), 'version').asc(), False, False),
        (VersionWithClassBasedProperties, Concat(Value('V'), 'version').asc(), False, True),
        (VersionWithDecoratorBasedProperties, Concat(Value('V'), 'version').asc(), False, True),
        (VersionWithClassBasedProperties, Concat(Value('V'), 'version').desc(), True, False),
        (VersionWithDecoratorBasedProperties, Concat(Value('V'), 'version').desc(), True, False),
        (VersionWithClassBasedProperties, Concat(Value('V'), 'version').desc(), True, True),
        (VersionWithDecoratorBasedProperties, Concat(Value('V'), 'version').desc(), True, True),
    ])
    def test_single_model(self, model, order_by, reverse, with_selection):
        queryset = model.objects.all()
        if with_selection:
            queryset = queryset.select_properties('version')
        results = list(queryset.order_by(order_by))
        assert results == sorted(results, key=lambda version: version.version, reverse=reverse)
        # Check that ordering by a property annotation does not lead to a
        # selection of the property annotation
        assert all(model.version._has_cached_value(version) is with_selection for version in results)
