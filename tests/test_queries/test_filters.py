# encoding: utf-8

import pytest

from django import VERSION as DJANGO_VERSION
from django.db import models
from django.utils import six

from ..models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                      CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties,
                      VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class TestFilterWithoutAnnotations(object):

    @pytest.mark.parametrize('model, filters, expected_count, expected_major_minor', [
        # Test that filter that don't involve queryable properties still work
        (VersionWithClassBasedProperties, models.Q(major=2, minor=0), 2, '2.0'),
        (VersionWithDecoratorBasedProperties, models.Q(major=2, minor=0), 2, '2.0'),
        (VersionWithClassBasedProperties, models.Q(minor=2) | models.Q(patch=3), 2, '1.2'),
        (VersionWithDecoratorBasedProperties, models.Q(minor=2) | models.Q(patch=3), 2, '1.2'),
        # All querysets are expected to return objects with the same
        # major_minor value (major_minor parameter).
        (VersionWithClassBasedProperties, models.Q(major_minor='1.2'), 2, '1.2'),
        (VersionWithDecoratorBasedProperties, models.Q(major_minor='1.2'), 2, '1.2'),
        # Also test that using non-property filters still work and can be used
        # together with filters for queryable properties
        (VersionWithClassBasedProperties, models.Q(major_minor='1.3') & models.Q(major=1), 4, '1.3'),
        (VersionWithDecoratorBasedProperties, models.Q(major_minor='1.3') & models.Q(major=1), 4, '1.3'),
        (VersionWithClassBasedProperties, models.Q(major_minor='1.3') | models.Q(patch=1), 4, '1.3'),
        (VersionWithDecoratorBasedProperties, models.Q(major_minor='1.3') | models.Q(patch=1), 4, '1.3'),
        # Also test nested filters
        (VersionWithClassBasedProperties, (models.Q(major_minor='2.0') | models.Q(patch=0)) & models.Q(minor=0),
         2, '2.0'),
        (VersionWithDecoratorBasedProperties, (models.Q(major_minor='2.0') | models.Q(patch=0)) & models.Q(minor=0),
         2, '2.0'),
    ])
    def test_simple_filter(self, model, filters, expected_count, expected_major_minor):
        queryset = model.objects.filter(filters)
        assert len(queryset) == expected_count
        assert all(obj.major_minor == expected_major_minor for obj in queryset)

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_filter_without_required_annotation(self, model):
        # Filtering the 'version' property is also based on filtering the
        # 'major_minor' property, so this test also tests properties that build
        # on each other
        queryset = model.objects.filter(version='1.2.3')
        assert 'version' not in queryset.query.annotations
        assert len(queryset) == 2
        assert all(obj.version == '1.2.3' for obj in queryset)

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_filter_without_required_annotation_across_relation(self, model):
        # Filtering the 'version' property is also based on filtering the
        # 'major_minor' property, so this test also tests properties that build
        # on each other
        queryset = model.objects.filter(versions__version='1.2.3')
        assert 'versions__version' not in queryset.query.annotations
        assert len(queryset) == 2
        assert all(obj.versions.filter(version='1.2.3').exists() for obj in queryset)

    @pytest.mark.parametrize('model, filters, expected_remaining_count', [
        (VersionWithClassBasedProperties, models.Q(major_minor='1.3'), 4),
        (VersionWithDecoratorBasedProperties, models.Q(major_minor='1.3'), 4),
        (VersionWithClassBasedProperties, models.Q(version='2.0.0'), 6),
        (VersionWithDecoratorBasedProperties, models.Q(major_minor='2.0.0'), 6),
        (VersionWithClassBasedProperties, models.Q(major_minor='1.3', patch=1), 6),
        (VersionWithDecoratorBasedProperties, models.Q(major_minor='1.3', patch=1), 6),
        (VersionWithClassBasedProperties, models.Q(major_minor='1.3') | models.Q(version='2.0.0'), 2),
        (VersionWithDecoratorBasedProperties, models.Q(major_minor='1.3') | models.Q(version='2.0.0'), 2),
        # Filters across relations
        (ApplicationWithClassBasedProperties, models.Q(versions__version='2.0.0'), 0),
        (ApplicationWithDecoratorBasedProperties, models.Q(versions__version='2.0.0'), 0),
    ])
    def test_delete_query(self, model, filters, expected_remaining_count):
        model.objects.filter(filters).delete()
        assert model.objects.count() == expected_remaining_count


class TestFilterWithAggregateAnnotation(object):

    @pytest.mark.parametrize('model, filters, expected_count', [
        (ApplicationWithClassBasedProperties, models.Q(version_count__gt=3), 2),
        (ApplicationWithClassBasedProperties, models.Q(version_count=4, name__contains='cool'), 1),
        (ApplicationWithClassBasedProperties, models.Q(version_count=4) | models.Q(name__contains='cool'), 2),
        (ApplicationWithClassBasedProperties, models.Q(version_count__gt=3, major_sum__gt=5), 0),
        (ApplicationWithClassBasedProperties, models.Q(version_count__gt=3) | models.Q(major_sum__gt=5), 2),
        (ApplicationWithDecoratorBasedProperties, models.Q(version_count__gt=3), 2),
        (ApplicationWithDecoratorBasedProperties, models.Q(version_count=4, name__contains='cool'), 1),
        (ApplicationWithDecoratorBasedProperties, models.Q(version_count=4) | models.Q(name__contains='cool'), 2),
        (ApplicationWithDecoratorBasedProperties, models.Q(version_count__gt=3, major_sum__gt=5), 0),
        (ApplicationWithDecoratorBasedProperties, models.Q(version_count__gt=3) | models.Q(major_sum__gt=5), 2),
    ])
    def test_single_model(self, model, filters, expected_count):
        queryset = model.objects.filter(filters)
        assert 'version_count' in queryset.query.annotations
        assert len(queryset) == expected_count
        # Check that a property annotation used implicitly by a filter does not
        # lead to a selection of the property annotation
        assert all(not model.version_count._has_cached_value(app) for app in queryset)

    @pytest.mark.parametrize('model', [CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties])
    def test_across_relation(self, model):
        # A query containing an aggregate across a relation is still only
        # grouped by fields of the query's model, so in this case the version
        # count is the total number of application versions per category.
        queryset = model.objects.filter(applications__version_count=4)
        assert 'applications__version_count' in queryset.query.annotations
        assert queryset.count() == 1
        assert model.objects.filter(applications__version_count=8).count() == 1

    @pytest.mark.parametrize('model, filters, expected_remaining_count', [
        (ApplicationWithClassBasedProperties, models.Q(version_count=4, name__contains='cool'), 1),
        (ApplicationWithDecoratorBasedProperties, models.Q(version_count=4, name__contains='cool'), 1),
        # Filters across relations
        (CategoryWithClassBasedProperties, models.Q(applications__version_count=4, name__contains='Windows'), 1),
        (CategoryWithDecoratorBasedProperties, models.Q(applications__version_count=4, name__contains='Windows'), 1),
    ])
    def test_delete_query(self, model, filters, expected_remaining_count):
        model.objects.filter(filters).delete()
        assert model.objects.count() == expected_remaining_count

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_filter_implementation_used_despite_present_annotation(self, monkeypatch, model):
        # Patch the property to have a filter that is always True, then use a
        # condition that would be False without the patch.
        monkeypatch.setattr(model.version_count, 'get_filter', lambda cls, lookup, value: models.Q(pk__gt=0))
        queryset = model.objects.select_properties('version_count').filter(version_count__gt=5)
        assert '"id" > 0' in six.text_type(queryset.query)
        assert queryset.count() == 2


@pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
class TestFilterWithExpressionAnnotation(object):

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_single_model(self, model):
        queryset = model.objects.filter(changes_or_default='(No data)')
        assert 'changes_or_default' in queryset.query.annotations
        assert len(queryset) == 6
        assert all(obj.changes_or_default == '(No data)' for obj in queryset)
        # Check that a property annotation used implicitly by a filter does not
        # lead to a selection of the property annotation
        assert all(not model.changes_or_default._has_cached_value(version) for version in queryset)

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_across_relation(self, model):
        queryset = model.objects.filter(versions__changes_or_default='(No data)')
        assert 'versions__changes_or_default' in queryset.query.annotations
        assert len(queryset) == 6
        assert all(obj.versions.filter(changes_or_default='(No data)').exists() for obj in queryset)
        assert queryset.distinct().count() == 2

    @pytest.mark.parametrize('model', [CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties])
    def test_dependency_across_relation(self, model):
        queryset = model.objects.filter(applications__lowered_version_changes='amazing new features')
        assert 'applications__lowered_version_changes' in queryset.query.annotations
        assert len(queryset) == 3
        assert queryset.distinct().count() == 2

    @pytest.mark.parametrize('model, filters, expected_remaining_count', [
        (VersionWithClassBasedProperties, models.Q(changes_or_default='(No data)', major=1), 2),
        (VersionWithDecoratorBasedProperties, models.Q(changes_or_default='(No data)', major=1), 2),
        # Filters across relations
        (ApplicationWithClassBasedProperties, models.Q(versions__changes_or_default='(No data)'), 0),
        (ApplicationWithDecoratorBasedProperties, models.Q(versions__changes_or_default='(No data)'), 0),
    ])
    def test_delete_query(self, model, filters, expected_remaining_count):
        model.objects.filter(filters).delete()
        assert model.objects.count() == expected_remaining_count

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_filter_implementation_used_despite_present_annotation(self, model):
        queryset = model.objects.select_properties('version').filter(version='2.0.0')
        pseudo_sql = six.text_type(queryset.query)
        assert '"major" = 2' in pseudo_sql
        assert '"minor" = 0' in pseudo_sql
        assert '"patch" = 0' in pseudo_sql
        assert queryset.count() == 2


@pytest.mark.skipif(DJANGO_VERSION < (1, 11), reason="Explicit subqueries didn't exist before Django 1.11")
class TestFilterWithSubqueryAnnotation(object):

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_single_model(self, model):
        version_model = model.objects.all()[0].versions.model
        version_model.objects.filter(version='2.0.0')[0].delete()
        queryset = model.objects.filter(highest_version='2.0.0')
        assert 'highest_version' in queryset.query.annotations
        assert len(queryset) == 1
        application = queryset[0]
        assert application.versions.filter(major=2, minor=0, patch=0).exists()
        # Check that a property annotation used implicitly by a filter does not
        # lead to a selection of the property annotation
        assert not model.highest_version._has_cached_value(application)

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_across_relation(self, model):
        model.objects.filter(version='2.0.0')[0].delete()
        queryset = model.objects.filter(application__highest_version='2.0.0')
        assert 'application__highest_version' in queryset.query.annotations
        assert len(queryset) == 4
        assert all(obj.application.highest_version == '2.0.0' for obj in queryset)

    @pytest.mark.parametrize('model, filters, expected_remaining_count', [
        (ApplicationWithClassBasedProperties, models.Q(highest_version='2.0.0', name__contains='cool'), 1),
        (ApplicationWithDecoratorBasedProperties, models.Q(highest_version='2.0.0', name__contains='cool'), 1),
        # Filters across relations
        (CategoryWithClassBasedProperties, models.Q(applications__highest_version='2.0.0'), 0),
        (CategoryWithDecoratorBasedProperties, models.Q(applications__highest_version='2.0.0'), 0),
    ])
    def test_delete_query(self, model, filters, expected_remaining_count):
        model.objects.filter(filters).delete()
        assert model.objects.count() == expected_remaining_count
