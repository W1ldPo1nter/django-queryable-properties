# encoding: utf-8

import pytest

from six.moves import cPickle

from .app_management.models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                                    VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)


@pytest.mark.django_db
@pytest.mark.usefixtures('versions')
class TestQueryablePropertiesQuerySetMixin(object):

    def assert_queryset_picklable(self, queryset, selected_descriptors=()):
        expected_results = list(queryset)
        serialized_queryset = cPickle.dumps(queryset)
        deserialized_queryset = cPickle.loads(serialized_queryset)
        assert list(deserialized_queryset) == expected_results
        for descriptor in selected_descriptors:
            assert all(descriptor.has_cached_value(obj) for obj in deserialized_queryset)

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_pickle_model_instance_queryset(self, model):
        queryset = model.objects.filter(version_count=4).order_by('name').select_properties('version_count')
        self.assert_queryset_picklable(queryset, (model.version_count,))

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_pickle_values_queryset(self, model):
        queryset = model.objects.order_by('-pk').select_properties('version_count').values('name', 'version_count')
        self.assert_queryset_picklable(queryset)

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_pickle_values_list_queryset(self, model):
        queryset = model.objects.order_by('pk').select_properties('version_count').values_list('name', 'version_count')
        self.assert_queryset_picklable(queryset)

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_pickle_dates_queryset(self, model):
        queryset = model.objects.filter(application__version_count=3).dates('supported_from', 'year')
        self.assert_queryset_picklable(queryset)
