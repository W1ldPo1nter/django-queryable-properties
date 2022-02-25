# encoding: utf-8

import pytest
from mock import Mock, patch
from six.moves import cPickle

from queryable_properties.compat import ModelIterable
from queryable_properties.managers import LegacyBaseIterable, QueryablePropertiesIterableMixin
from .app_management.models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                                    VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class DummyIterable(QueryablePropertiesIterableMixin, ModelIterable or LegacyBaseIterable):
    pass


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


class TestLegacyBaseIterable(object):

    def test_initializer(self):
        queryset = ApplicationWithClassBasedProperties.objects.all()
        iterable = LegacyBaseIterable(queryset)
        assert iterable.queryset is queryset

    def test_iter(self):
        for queryset in (
            ApplicationWithClassBasedProperties.objects.order_by('pk'),
            ApplicationWithClassBasedProperties.objects.order_by('pk').values('pk', 'name'),
            ApplicationWithClassBasedProperties.objects.order_by('pk').values_list('pk', 'name'),
            VersionWithClassBasedProperties.objects.dates('supported_from', 'year'),
        ):
            iterable = LegacyBaseIterable(queryset)
            assert list(iterable) == list(queryset)


class TestQueryablePropertiesIterableMixin(object):

    def test_initializer(self):
        queryset = ApplicationWithClassBasedProperties.objects.order_by('pk')
        iterable = DummyIterable(queryset)
        assert iterable.queryset is not queryset
        assert list(queryset) == list(iterable.queryset)

    def test_postprocess_queryable_properties(self):
        iterable = DummyIterable(ApplicationWithClassBasedProperties.objects.order_by('pk'))
        application = ApplicationWithClassBasedProperties()
        assert iterable._postprocess_queryable_properties(application) is application

    def test_iter(self):
        queryset = ApplicationWithClassBasedProperties.objects.order_by('pk')
        iterable = DummyIterable(queryset)
        mock_setup = Mock()
        mock_postprocess = Mock(side_effect=lambda obj: obj)
        with patch.multiple(iterable, _setup_queryable_properties=mock_setup,
                            _postprocess_queryable_properties=mock_postprocess):
            applications = list(iterable)
        assert applications == list(queryset)
        mock_setup.assert_called_once_with()
        assert mock_postprocess.call_count == len(applications)
        for application in applications:
            mock_postprocess.assert_any_call(application)
