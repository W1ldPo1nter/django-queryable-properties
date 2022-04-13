# -*- coding: utf-8 -*-

from itertools import groupby

import pytest

from queryable_properties.exceptions import QueryablePropertyDoesNotExist
from queryable_properties.properties import QueryableProperty
from queryable_properties.utils import get_queryable_property, prefetch_queryable_properties
from queryable_properties.utils.internal import get_queryable_property_descriptor
from ..app_management.models import (
    ApplicationWithClassBasedProperties, CategoryWithClassBasedProperties, VersionWithClassBasedProperties,
    VersionWithDecoratorBasedProperties,
)


class TestGetQueryableProperty(object):

    @pytest.mark.parametrize('model, property_name', [
        (VersionWithClassBasedProperties, 'major_minor'),
        (VersionWithDecoratorBasedProperties, 'major_minor'),
        (VersionWithClassBasedProperties, 'version'),
        (VersionWithDecoratorBasedProperties, 'version'),
    ])
    def test_property_found(self, model, property_name):
        prop = get_queryable_property(model, property_name)
        assert isinstance(prop, QueryableProperty)

    @pytest.mark.parametrize('model, property_name', [
        (VersionWithClassBasedProperties, 'non_existent'),
        (VersionWithDecoratorBasedProperties, 'non_existent'),
        (VersionWithClassBasedProperties, 'major'),  # Existing model field
        (VersionWithDecoratorBasedProperties, 'major'),  # Existing model field
    ])
    def test_exception(self, model, property_name):
        with pytest.raises(QueryablePropertyDoesNotExist):
            get_queryable_property(model, property_name)


@pytest.mark.django_db
class TestPrefetchQueryableProperties(object):

    def assert_not_cached(self, descriptor, *model_instances):
        assert all(not descriptor.has_cached_value(instance) for instance in model_instances)

    def assert_cached(self, descriptor, *model_instances):
        assert all(descriptor.has_cached_value(instance) for instance in model_instances)
        assert all(descriptor.get_cached_value(instance) == descriptor.prop.get_value(instance)
                   for instance in model_instances)

    def test_no_instances(self):
        instances = []
        prefetch_queryable_properties(instances, 'whatever')
        assert instances == []

    @pytest.mark.parametrize('property_names', [
        (),
        ('version_count',),
        ('version_count', 'major_sum'),
    ])
    @pytest.mark.usefixtures('versions')
    def test_local_property(self, applications, property_names):
        descriptors = [get_queryable_property_descriptor(ApplicationWithClassBasedProperties, name)
                       for name in property_names]
        applications = applications[:2]
        for descriptor in descriptors:
            self.assert_not_cached(descriptor, *applications)
        prefetch_queryable_properties(applications, *property_names)
        for descriptor in descriptors:
            self.assert_cached(descriptor, *applications)

    @pytest.mark.usefixtures('versions')
    def test_2o_relation_property(self):
        descriptor = get_queryable_property_descriptor(ApplicationWithClassBasedProperties, 'version_count')
        versions = list(VersionWithClassBasedProperties.objects.select_related('application'))
        self.assert_not_cached(descriptor, *(version.application for version in versions))
        prefetch_queryable_properties(versions, 'application__version_count')
        self.assert_cached(descriptor, *(version.application for version in versions))

    @pytest.mark.usefixtures('versions')
    def test_2m_relation_property(self):
        descriptor = get_queryable_property_descriptor(ApplicationWithClassBasedProperties, 'version_count')
        categories = list(CategoryWithClassBasedProperties.objects.prefetch_related('applications'))
        for category in categories:
            self.assert_not_cached(descriptor, *category.applications.all())
        prefetch_queryable_properties(categories, 'applications__version_count')
        for category in categories:
            self.assert_cached(descriptor, *category.applications.all())

    @pytest.mark.usefixtures('versions')
    def test_different_types(self, categories, applications):
        model_instances = categories[:2] + applications
        grouped_instances = {cls: list(instances) for cls, instances in
                             groupby(model_instances, key=lambda instance: instance.__class__)}
        for cls, instances in grouped_instances.items():
            self.assert_not_cached(get_queryable_property_descriptor(cls, 'version_count'), *instances)
        prefetch_queryable_properties(model_instances, 'version_count')
        for cls, instances in grouped_instances.items():
            self.assert_cached(get_queryable_property_descriptor(cls, 'version_count'), *instances)

    @pytest.mark.usefixtures('versions')
    def test_refresh_cache(self):
        """
        Test that prefetch_queryable_properties can be used to update already
        cached values on instances.
        """
        descriptor = get_queryable_property_descriptor(ApplicationWithClassBasedProperties, 'version_count')
        application = ApplicationWithClassBasedProperties.objects.select_properties('version_count')[0]
        self.assert_cached(descriptor, application)
        application.versions.all().delete()
        assert application.version_count > 0  # The cached value is still present
        prefetch_queryable_properties([application], 'version_count')
        self.assert_cached(descriptor, application)

    @pytest.mark.parametrize('property_name, expected_exception', [
        ('non_existent', QueryablePropertyDoesNotExist),
        ('application__non_existent', QueryablePropertyDoesNotExist),
        ('non_existent__non_existent', AttributeError),
    ])
    def test_invalid_propery_path(self, versions, property_name, expected_exception):
        with pytest.raises(expected_exception):
            prefetch_queryable_properties(versions, property_name)
