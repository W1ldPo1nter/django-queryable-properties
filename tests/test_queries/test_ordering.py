# encoding: utf-8

import pytest

from django import VERSION as DJANGO_VERSION

from ..app_management.models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                                     VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)
from ..conftest import Concat, Value

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class TestAggregateAnnotations(object):

    @pytest.mark.parametrize('model, order_by, reverse, with_selection', [
        # All parametrizations are expected to yield results ordered by the
        # version count (ASC/DESC depending on the reverse parameter).
        (ApplicationWithClassBasedProperties, ('version_count',), False, False),
        (ApplicationWithDecoratorBasedProperties, ('version_count',), False, False),
        (ApplicationWithClassBasedProperties, ('version_count',), False, True),
        (ApplicationWithDecoratorBasedProperties, ('version_count',), False, True),
        (ApplicationWithClassBasedProperties, ('version_count', '-name'), False, False),
        (ApplicationWithDecoratorBasedProperties, ('version_count', '-name'), False, False),
        (ApplicationWithClassBasedProperties, ('-version_count',), True, False),
        (ApplicationWithDecoratorBasedProperties, ('-version_count',), True, False),
        (ApplicationWithClassBasedProperties, ('-version_count',), True, True),
        (ApplicationWithDecoratorBasedProperties, ('-version_count',), True, True),
        (ApplicationWithClassBasedProperties, ('-version_count', 'name'), True, False),
        (ApplicationWithDecoratorBasedProperties, ('-version_count', 'name'), True, False),
    ])
    def test_single_model(self, model, order_by, reverse, with_selection):
        model.objects.all()[0].versions.all()[0].delete()
        queryset = model.objects.all()
        if with_selection:
            queryset = queryset.select_properties('version_count')
        results = list(queryset.order_by(*order_by))
        assert results == sorted(results, key=lambda application: application.version_count, reverse=reverse)
        # Check that ordering by a property annotation does not lead to a
        # selection of the property annotation.
        assert all(model.version_count._has_cached_value(application) is with_selection for application in results)

    @pytest.mark.parametrize('model, order_by, reverse', [
        # All parametrizations are expected to yield results ordered by the
        # version count (ASC/DESC depending on the reverse parameter).
        (VersionWithClassBasedProperties, ('application__version_count',), False),
        (VersionWithDecoratorBasedProperties, ('application__version_count',), False),
        (VersionWithClassBasedProperties, ('application__version_count', '-application__name'), False),
        (VersionWithDecoratorBasedProperties, ('application__version_count', '-application__name'), False),
        (VersionWithClassBasedProperties, ('-application__version_count',), True),
        (VersionWithDecoratorBasedProperties, ('-application__version_count',), True),
        (VersionWithClassBasedProperties, ('-application__version_count', 'application__name'), True),
        (VersionWithDecoratorBasedProperties, ('-application__version_count', 'application__name'), True),
    ])
    def test_across_relation(self, model, order_by, reverse):
        model.objects.all()[0].delete()  # Create a different version count for the application fixtures.
        results = list(model.objects.order_by(*order_by))
        assert results == sorted(results, key=lambda version: version.application.version_count, reverse=reverse)


@pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
class TestExpressionAnnotations(object):

    @pytest.mark.parametrize('model, order_by, reverse, with_selection', [
        # All parametrizations are expected to yield results ordered by the
        # full version (ASC/DESC depending on the reverse parameter).
        (VersionWithClassBasedProperties, ('version',), False, False),
        (VersionWithDecoratorBasedProperties, ('version',), False, False),
        (VersionWithClassBasedProperties, ('version',), False, True),
        (VersionWithDecoratorBasedProperties, ('version',), False, True),
        (VersionWithClassBasedProperties, ('version', '-major'), False, False),
        (VersionWithDecoratorBasedProperties, ('version', '-major'), False, False),
        (VersionWithClassBasedProperties, ('-version',), True, False),
        (VersionWithDecoratorBasedProperties, ('-version',), True, False),
        (VersionWithClassBasedProperties, ('-version',), True, True),
        (VersionWithDecoratorBasedProperties, ('-version',), True, True),
        (VersionWithClassBasedProperties, ('-version', 'minor'), True, False),
        (VersionWithDecoratorBasedProperties, ('-version', 'minor'), True, False),
        (VersionWithClassBasedProperties, (Concat(Value('V'), 'version').asc(),), False, False),
        (VersionWithDecoratorBasedProperties, (Concat(Value('V'), 'version').asc(),), False, False),
        (VersionWithClassBasedProperties, (Concat(Value('V'), 'version').asc(),), False, True),
        (VersionWithDecoratorBasedProperties, (Concat(Value('V'), 'version').asc(),), False, True),
        (VersionWithClassBasedProperties, (Concat(Value('V'), 'version').asc(), '-patch'), False, False),
        (VersionWithDecoratorBasedProperties, (Concat(Value('V'), 'version').asc(), '-patch'), False, False),
        (VersionWithClassBasedProperties, (Concat(Value('V'), 'version').desc(),), True, False),
        (VersionWithDecoratorBasedProperties, (Concat(Value('V'), 'version').desc(),), True, False),
        (VersionWithClassBasedProperties, (Concat(Value('V'), 'version').desc(),), True, True),
        (VersionWithDecoratorBasedProperties, (Concat(Value('V'), 'version').desc(),), True, True),
        (VersionWithClassBasedProperties, (Concat(Value('V'), 'version').desc(), 'major'), True, False),
        (VersionWithDecoratorBasedProperties, (Concat(Value('V'), 'version').desc(), 'major'), True, False),
    ])
    def test_single_model(self, model, order_by, reverse, with_selection):
        queryset = model.objects.all()
        if with_selection:
            queryset = queryset.select_properties('version')
        results = list(queryset.order_by(*order_by))
        assert results == sorted(results, key=lambda version: version.version, reverse=reverse)
        # Check that ordering by a property annotation does not lead to a
        # selection of the property annotation
        assert all(model.version._has_cached_value(version) is with_selection for version in results)

    @pytest.mark.parametrize('model, order_by, expected_names', [
        (ApplicationWithClassBasedProperties, ('versions__version',),
         ['My cool App', 'Another App', 'My cool App', 'Another App']),
        (ApplicationWithDecoratorBasedProperties, ('versions__version',),
         ['My cool App', 'Another App', 'My cool App', 'Another App']),
        (ApplicationWithClassBasedProperties, ('versions__version', '-name'),
         ['My cool App', 'Another App', 'My cool App', 'Another App']),
        (ApplicationWithDecoratorBasedProperties, ('versions__version', '-name'),
         ['My cool App', 'Another App', 'My cool App', 'Another App']),
        (ApplicationWithClassBasedProperties, ('-versions__version',),
         ['Another App', 'My cool App', 'Another App', 'My cool App']),
        (ApplicationWithDecoratorBasedProperties, ('-versions__version',),
         ['Another App', 'My cool App', 'Another App', 'My cool App']),
        (ApplicationWithClassBasedProperties, ('-versions__version', 'name'),
         ['Another App', 'My cool App', 'Another App', 'My cool App']),
        (ApplicationWithDecoratorBasedProperties, ('-versions__version', 'name'),
         ['Another App', 'My cool App', 'Another App', 'My cool App']),
        (ApplicationWithClassBasedProperties, (Concat(Value('V'), 'versions__version').asc(),),
         ['My cool App', 'Another App', 'My cool App', 'Another App']),
        (ApplicationWithDecoratorBasedProperties, (Concat(Value('V'), 'versions__version').asc(),),
         ['My cool App', 'Another App', 'My cool App', 'Another App']),
        (ApplicationWithClassBasedProperties, (Concat(Value('V'), 'versions__version').asc(), '-name'),
         ['My cool App', 'Another App', 'My cool App', 'Another App']),
        (ApplicationWithDecoratorBasedProperties, (Concat(Value('V'), 'versions__version').asc(), '-name'),
         ['My cool App', 'Another App', 'My cool App', 'Another App']),
        (ApplicationWithClassBasedProperties, (Concat(Value('V'), 'versions__version').desc(),),
         ['Another App', 'My cool App', 'Another App', 'My cool App']),
        (ApplicationWithDecoratorBasedProperties, (Concat(Value('V'), 'versions__version').desc(),),
         ['Another App', 'My cool App', 'Another App', 'My cool App']),
        (ApplicationWithClassBasedProperties, (Concat(Value('V'), 'versions__version').desc(), 'name'),
         ['Another App', 'My cool App', 'Another App', 'My cool App']),
        (ApplicationWithDecoratorBasedProperties, (Concat(Value('V'), 'versions__version').desc(), 'name'),
         ['Another App', 'My cool App', 'Another App', 'My cool App']),
    ])
    def test_across_relation(self, model, order_by, expected_names):
        version_model = (VersionWithClassBasedProperties if 'ClassBased' in model.__name__
                         else VersionWithDecoratorBasedProperties)
        # Delete versions to make every version number unique
        version_model.objects.get(version='2.0.0', application__name__contains='cool').delete()
        version_model.objects.get(version='1.3.0', application__name__contains='cool').delete()
        version_model.objects.get(version='1.3.1', application__name__startswith='Another').delete()
        version_model.objects.get(version='1.2.3', application__name__startswith='Another').delete()
        assert [app.name for app in model.objects.order_by(*order_by)] == expected_names


@pytest.mark.skipif(DJANGO_VERSION < (1, 11), reason="Explicit subqueries didn't exist before Django 1.11")
class TestSubqueryAnnotations(object):

    @pytest.mark.parametrize('model, order_by, reverse, with_selection', [
        # All parametrizations are expected to yield results ordered by the
        # full version (ASC/DESC depending on the reverse parameter).
        (ApplicationWithClassBasedProperties, ('highest_version',), False, False),
        (ApplicationWithDecoratorBasedProperties, ('highest_version',), False, False),
        (ApplicationWithClassBasedProperties, ('highest_version',), False, True),
        (ApplicationWithDecoratorBasedProperties, ('highest_version',), False, True),
        (ApplicationWithClassBasedProperties, ('highest_version', '-name'), False, False),
        (ApplicationWithDecoratorBasedProperties, ('highest_version', '-name'), False, False),
        (ApplicationWithClassBasedProperties, ('-highest_version',), True, False),
        (ApplicationWithDecoratorBasedProperties, ('-highest_version',), True, False),
        (ApplicationWithClassBasedProperties, ('-highest_version',), True, True),
        (ApplicationWithDecoratorBasedProperties, ('-highest_version',), True, True),
        (ApplicationWithClassBasedProperties, ('-highest_version', 'name'), True, False),
        (ApplicationWithDecoratorBasedProperties, ('-highest_version', 'name'), True, False),
        (ApplicationWithClassBasedProperties, (Concat(Value('V'), 'highest_version').asc(),), False, False),
        (ApplicationWithDecoratorBasedProperties, (Concat(Value('V'), 'highest_version').asc(),), False, False),
        (ApplicationWithClassBasedProperties, (Concat(Value('V'), 'highest_version').asc(),), False, True),
        (ApplicationWithDecoratorBasedProperties, (Concat(Value('V'), 'highest_version').asc(),), False, True),
        (ApplicationWithClassBasedProperties, (Concat(Value('V'), 'highest_version').asc(), '-name'), False, False),
        (ApplicationWithDecoratorBasedProperties, (Concat(Value('V'), 'highest_version').asc(), '-name'), False, False),
        (ApplicationWithClassBasedProperties, (Concat(Value('V'), 'highest_version').desc(),), True, False),
        (ApplicationWithDecoratorBasedProperties, (Concat(Value('V'), 'highest_version').desc(),), True, False),
        (ApplicationWithClassBasedProperties, (Concat(Value('V'), 'highest_version').desc(),), True, True),
        (ApplicationWithDecoratorBasedProperties, (Concat(Value('V'), 'highest_version').desc(),), True, True),
        (ApplicationWithClassBasedProperties, (Concat(Value('V'), 'highest_version').desc(), 'name'), True, False),
        (ApplicationWithDecoratorBasedProperties, (Concat(Value('V'), 'highest_version').desc(), 'name'), True, False),
    ])
    def test_single_model(self, model, order_by, reverse, with_selection):
        model.objects.all()[0].versions.get(version='2.0.0').delete()
        queryset = model.objects.all()
        if with_selection:
            queryset = queryset.select_properties('highest_version')
        results = list(queryset.order_by(*order_by))
        assert results == sorted(results, key=lambda app: app.highest_version, reverse=reverse)
        # Check that ordering by a property annotation does not lead to a
        # selection of the property annotation
        assert all(model.highest_version._has_cached_value(app) is with_selection for app in results)

    @pytest.mark.parametrize('model, order_by, reverse', [
        # All parametrizations are expected to yield results ordered by the
        # application's highest version and version pk (ASC/DESC depending on
        # the reverse parameter).
        (VersionWithClassBasedProperties, ('application__highest_version', 'pk'), False),
        (VersionWithDecoratorBasedProperties, ('application__highest_version', 'pk'), False),
        (VersionWithClassBasedProperties, ('-application__highest_version', '-pk'), True),
        (VersionWithDecoratorBasedProperties, ('-application__highest_version', '-pk'), True),
        (VersionWithClassBasedProperties, (Concat(Value('V'), 'application__highest_version').asc(), 'pk'), False),
        (VersionWithDecoratorBasedProperties, (Concat(Value('V'), 'application__highest_version').asc(), 'pk'), False),
        (VersionWithClassBasedProperties, (Concat(Value('V'), 'application__highest_version').desc(), '-pk'), True),
        (VersionWithDecoratorBasedProperties, (Concat(Value('V'), 'application__highest_version').desc(), '-pk'), True),
    ])
    def test_across_relation(self, model, order_by, reverse):
        model.objects.filter(version='2.0.0')[0].delete()
        results = list(model.objects.order_by(*order_by))
        assert results == sorted(
            results, key=lambda version: (version.application.highest_version, version.pk), reverse=reverse)
