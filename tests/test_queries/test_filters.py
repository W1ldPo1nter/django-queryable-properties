# encoding: utf-8

import pytest

import six
from django import VERSION as DJANGO_VERSION
from django.db import models

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
        assert queryset.count() == len(queryset) == expected_count
        assert all(obj.major_minor == expected_major_minor for obj in queryset)

    @pytest.mark.parametrize('model, property_name, value, expected_count, record_checker', [
        # Filtering the 'version' property is also based on filtering the
        # 'major_minor' property, so this test also tests properties that build
        # on each other.
        (VersionWithClassBasedProperties, 'version', '1.2.3', 2, lambda obj: obj.version == '1.2.3'),
        (VersionWithDecoratorBasedProperties, 'version', '1.2.3', 2, lambda obj: obj.version == '1.2.3'),
        # Filters across relations
        (ApplicationWithClassBasedProperties, 'versions__version', '1.2.3', 2,
         lambda obj: obj.versions.filter(version='1.2.3').exists()),
        (ApplicationWithDecoratorBasedProperties, 'versions__version', '1.2.3', 2,
         lambda obj: obj.versions.filter(version='1.2.3').exists()),
    ])
    def test_filter_without_required_annotation(self, model, property_name, value, expected_count, record_checker):
        queryset = model.objects.filter(**{property_name: value})
        assert property_name not in queryset.query.annotations
        assert queryset.count() == len(queryset) == expected_count
        assert all(record_checker(obj) for obj in queryset)

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

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_boolean_filter(self, model):
        v2_objects = model.objects.filter(is_version_2=True)
        non_v2_objects = model.objects.filter(is_version_2=False)
        assert len(v2_objects) == 2
        assert all(version.is_version_2 for version in v2_objects)
        assert len(non_v2_objects) == 6
        assert all(not version.is_version_2 for version in non_v2_objects)

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    @pytest.mark.parametrize('model, property_name, condition', [
        (VersionWithClassBasedProperties, 'major_minor', models.Q(major_minor='1.3')),
        (VersionWithDecoratorBasedProperties, 'major_minor', models.Q(major_minor='1.3')),
        (VersionWithClassBasedProperties, 'version', models.Q(version='1.3.0') | models.Q(version='1.3.1')),
        (VersionWithDecoratorBasedProperties, 'version', models.Q(version='1.3.0') | models.Q(version='1.3.1')),
    ])
    def test_filter_in_case_expression(self, model, property_name, condition):
        queryset = model.objects.annotate(is_13=models.Case(
            models.When(condition, then=1),
            default=0,
            output_field=models.IntegerField()
        ))
        assert property_name not in queryset.query.annotations
        assert all(bool(version.is_13) is (version.major_minor == '1.3') for version in queryset)

    @pytest.mark.skipif(DJANGO_VERSION < (2, 0), reason="Per-aggregate filters didn't exist before Django 2.0")
    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_filter_in_aggregate(self, model):
        queryset = model.objects.annotate(
            num_13=models.Count('versions', filter=models.Q(versions__major_minor='1.3')),
            num_200=models.Count('versions', filter=models.Q(versions__version='2.0.0'))
        )
        assert 'major_minor' not in queryset.query.annotations
        assert 'version' not in queryset.query.annotations
        for app in queryset:
            assert app.num_13 == 2
            assert app.num_200 == 1

    @pytest.mark.skipif(DJANGO_VERSION < (3, 0), reason="Conditional filters didn't exist before Django 3.0")
    @pytest.mark.parametrize('application_model, version_model', [
        (ApplicationWithClassBasedProperties, VersionWithClassBasedProperties),
        (ApplicationWithDecoratorBasedProperties, VersionWithDecoratorBasedProperties),
    ])
    def test_conditional_filter(self, application_model, version_model):
        version_model.objects.filter(major=2).first().delete()
        subquery = version_model.objects.filter(application_id=models.OuterRef('pk'), version='2.0.0')
        applications = application_model.objects.filter(models.Exists(subquery))
        assert len(applications) == 1
        assert applications[0].versions.filter(version='2.0.0').exists()


class TestFilterWithAggregateAnnotation(object):

    @pytest.mark.parametrize('model, property_name, filters, expected_count', [
        (ApplicationWithClassBasedProperties, 'version_count', models.Q(version_count__gt=3), 2),
        (ApplicationWithClassBasedProperties, 'version_count', models.Q(version_count=4, name__contains='cool'), 1),
        (ApplicationWithClassBasedProperties, 'version_count',
         models.Q(version_count=4) | models.Q(name__contains='cool'), 2),
        (ApplicationWithClassBasedProperties, 'version_count', models.Q(version_count__gt=3, major_sum__gt=5), 0),
        (ApplicationWithClassBasedProperties, 'version_count',
         models.Q(version_count__gt=3) | models.Q(major_sum__gt=5), 2),
        (ApplicationWithDecoratorBasedProperties, 'version_count', models.Q(version_count__gt=3), 2),
        (ApplicationWithDecoratorBasedProperties, 'version_count',
         models.Q(version_count=4, name__contains='cool'), 1),
        (ApplicationWithDecoratorBasedProperties, 'version_count',
         models.Q(version_count=4) | models.Q(name__contains='cool'), 2),
        (ApplicationWithDecoratorBasedProperties, 'version_count', models.Q(version_count__gt=3, major_sum__gt=5), 0),
        (ApplicationWithDecoratorBasedProperties, 'version_count',
         models.Q(version_count__gt=3) | models.Q(major_sum__gt=5), 2),
        # Filters across relations
        # A query containing an aggregate across a relation is still only
        # grouped by fields of the query's model, so in this case the version
        # count is the total number of application versions per category.
        (CategoryWithClassBasedProperties, 'applications__version_count', models.Q(applications__version_count=4), 1),
        (CategoryWithDecoratorBasedProperties, 'applications__version_count',
         models.Q(applications__version_count=4), 1),
        (CategoryWithClassBasedProperties, 'applications__version_count', models.Q(applications__version_count=8), 1),
        (CategoryWithDecoratorBasedProperties, 'applications__version_count',
         models.Q(applications__version_count=8), 1),
        (CategoryWithClassBasedProperties, 'applications__version_count',
         models.Q(applications__version_count=4, name__contains='Windows'), 1),
        (CategoryWithDecoratorBasedProperties, 'applications__version_count',
         models.Q(applications__version_count=4, name__contains='Windows'), 1),
        (CategoryWithClassBasedProperties, 'applications__version_count',
         models.Q(applications__version_count=8, name__contains='Windows'), 0),
        (CategoryWithDecoratorBasedProperties, 'applications__version_count',
         models.Q(applications__version_count=8, name__contains='Windows'), 0),
    ])
    def test_select_query(self, model, property_name, filters, expected_count):
        queryset = model.objects.filter(filters)
        assert property_name in queryset.query.annotations
        assert queryset.count() == len(queryset) == expected_count
        if '__' not in property_name:
            # Check that a property annotation used implicitly by a filter does
            # not lead to a selection of the property annotation.
            prop = getattr(model, property_name)
            assert all(not prop._has_cached_value(app) for app in queryset)

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
        assert queryset.count() == len(queryset) == 2


@pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
class TestFilterWithExpressionAnnotation(object):

    @pytest.mark.parametrize('model, property_name, filters, expected_count, expected_distinct_count, record_checker', [
        (VersionWithClassBasedProperties, 'changes_or_default', models.Q(changes_or_default='(No data)'), 6, 6,
         lambda obj: obj.changes_or_default == '(No data)'),
        (VersionWithDecoratorBasedProperties, 'changes_or_default', models.Q(changes_or_default='(No data)'), 6, 6,
         lambda obj: obj.changes_or_default == '(No data)'),
        (VersionWithClassBasedProperties, 'changes_or_default',
         models.Q(changes_or_default='(No data)') | models.Q(major=2), 8, 8,
         lambda obj: obj.changes_or_default == '(No data)' or obj.major == 2),
        (VersionWithDecoratorBasedProperties, 'changes_or_default',
         models.Q(changes_or_default='(No data)') | models.Q(major=2), 8, 8,
         lambda obj: obj.changes_or_default == '(No data)' or obj.major == 2),
        # Filters across relations
        (ApplicationWithClassBasedProperties, 'versions__changes_or_default',
         models.Q(versions__changes_or_default='(No data)'), 6, 2,
         lambda obj: obj.versions.filter(changes_or_default='(No data)').exists()),
        (ApplicationWithDecoratorBasedProperties, 'versions__changes_or_default',
         models.Q(versions__changes_or_default='(No data)'), 6, 2,
         lambda obj: obj.versions.filter(changes_or_default='(No data)').exists()),
        (ApplicationWithClassBasedProperties, 'versions__changes_or_default',
         models.Q(versions__minor=3) & models.Q(versions__changes_or_default='(No data)'), 4, 2,
         lambda obj: obj.versions.filter(changes_or_default='(No data)').exists()),
        (ApplicationWithDecoratorBasedProperties, 'versions__changes_or_default',
         models.Q(versions__minor=3) & models.Q(versions__changes_or_default='(No data)'), 4, 2,
         lambda obj: obj.versions.filter(changes_or_default='(No data)').exists()),
        # Filters across relations with dependencies across other relations
        (CategoryWithClassBasedProperties, 'applications__lowered_version_changes',
         models.Q(applications__lowered_version_changes='amazing new features'), 3, 2, None),
        (CategoryWithDecoratorBasedProperties, 'applications__lowered_version_changes',
         models.Q(applications__lowered_version_changes='amazing new features'), 3, 2, None),
    ])
    def test_select_query(self, model, property_name, filters, expected_count, expected_distinct_count, record_checker):
        queryset = model.objects.filter(filters)
        assert property_name in queryset.query.annotations
        assert queryset.distinct().count() == expected_distinct_count
        assert len(queryset) == expected_count
        if record_checker:
            assert all(record_checker(obj) for obj in queryset)
        if '__' not in property_name:
            # Check that a property annotation used implicitly by a filter does
            # not lead to a selection of the property annotation.
            prop = getattr(model, property_name)
            assert all(not prop._has_cached_value(version) for version in queryset)

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
        assert queryset.count() == len(queryset) == 2


@pytest.mark.skipif(DJANGO_VERSION < (1, 11), reason="Explicit subqueries didn't exist before Django 1.11")
class TestFilterWithSubqueryAnnotation(object):

    @pytest.mark.parametrize('model, property_name, filters, expected_count, record_checker', [
        (ApplicationWithClassBasedProperties, 'highest_version', models.Q(highest_version='2.0.0'), 1,
         lambda obj: obj.versions.filter(major=2, minor=0, patch=0).exists()),
        (ApplicationWithDecoratorBasedProperties, 'highest_version', models.Q(highest_version='2.0.0'), 1,
         lambda obj: obj.versions.filter(major=2, minor=0, patch=0).exists()),
        (ApplicationWithClassBasedProperties, 'highest_version',
         models.Q(highest_version='2.0.0') | models.Q(name__startswith='Another'), 1,
         lambda obj: obj.versions.filter(major=2, minor=0, patch=0).exists()),
        (ApplicationWithDecoratorBasedProperties, 'highest_version',
         models.Q(highest_version='2.0.0') | models.Q(name__startswith='Another'), 1,
         lambda obj: obj.versions.filter(major=2, minor=0, patch=0).exists()),
        # Filters across relations
        (VersionWithClassBasedProperties, 'application__highest_version',
         models.Q(application__highest_version='2.0.0'), 4, lambda obj: obj.application.highest_version == '2.0.0'),
        (VersionWithDecoratorBasedProperties, 'application__highest_version',
         models.Q(application__highest_version='2.0.0'), 4, lambda obj: obj.application.highest_version == '2.0.0'),
        (VersionWithClassBasedProperties, 'application__highest_version',
         models.Q(application__name__startswith='Another') & models.Q(application__highest_version='2.0.0'), 4,
         lambda obj: obj.application.highest_version == '2.0.0'),
        (VersionWithDecoratorBasedProperties, 'application__highest_version',
         models.Q(application__name__startswith='Another') & models.Q(application__highest_version='2.0.0'), 4,
         lambda obj: obj.application.highest_version == '2.0.0'),
    ])
    def test_select_query(self, model, property_name, filters, expected_count, record_checker):
        version_model = (VersionWithClassBasedProperties if 'ClassBased' in model.__name__
                         else VersionWithDecoratorBasedProperties)
        # Delete one version to create distinct constellations
        version_model.objects.get(version='2.0.0', application__name__contains='cool').delete()
        queryset = model.objects.filter(filters)
        assert property_name in queryset.query.annotations
        assert queryset.count() == len(queryset) == expected_count
        if '__' not in property_name:
            # Check that a property annotation used implicitly by a filter does
            # not lead to a selection of the property annotation.
            prop = getattr(model, property_name)
            assert all(not prop._has_cached_value(version) for version in queryset)

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
