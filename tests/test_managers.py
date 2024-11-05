import pickle

import pytest
from django.db.models.query import ModelIterable
from mock import Mock, patch

from queryable_properties.managers import (
    LegacyIterable,
    LegacyOrderingModelIterable,
    LegacyValuesIterable,
    QueryablePropertiesIterableMixin,
    QueryablePropertiesManager,
    QueryablePropertiesManagerMixin,
    QueryablePropertiesQuerySet,
    QueryablePropertiesQuerySetMixin,
)
from queryable_properties.query import QUERYING_PROPERTIES_MARKER
from queryable_properties.utils import get_queryable_property
from queryable_properties.utils.internal import QueryablePropertyReference, QueryPath
from .app_management.models import (
    ApplicationTag, ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
    VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties,
)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class DummyIterable(QueryablePropertiesIterableMixin, ModelIterable or LegacyIterable):
    pass


@pytest.fixture
def refs():
    model = ApplicationWithClassBasedProperties
    return {
        prop_name: QueryablePropertyReference(get_queryable_property(model, prop_name), model, QueryPath())
        for prop_name in ('major_sum', 'version_count')
    }


class TestQueryablePropertiesQuerySetMixin:

    def assert_queryset_picklable(self, queryset, selected_descriptors=()):
        expected_results = list(queryset)
        serialized_queryset = pickle.dumps(queryset)
        deserialized_queryset = pickle.loads(serialized_queryset)
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

    def test_apply_to(self, tags):
        queryset_without_properties = ApplicationTag.objects.all()
        assert not isinstance(queryset_without_properties, QueryablePropertiesQuerySetMixin)

        queryset = QueryablePropertiesQuerySetMixin.apply_to(queryset_without_properties)
        assert queryset is not queryset_without_properties
        assert isinstance(queryset, QueryablePropertiesQuerySetMixin)
        assert list(queryset_without_properties) == list(queryset)
        assert set(queryset.filter(applications__version_count=4)) == set(tags)


class TestQueryablePropertiesQuerySet:

    def test_get_for_model(self, tags):
        queryset_without_properties = ApplicationTag._default_manager.all()
        assert not isinstance(queryset_without_properties, QueryablePropertiesQuerySetMixin)

        queryset = QueryablePropertiesQuerySet.get_for_model(ApplicationTag)
        assert isinstance(queryset, QueryablePropertiesQuerySetMixin)
        assert list(queryset_without_properties) == list(queryset)
        assert set(queryset.filter(applications__version_count=4)) == set(tags)


class TestQueryablePropertiesManagerMixin:

    def test_apply_to(self, tags):
        assert not isinstance(ApplicationTag.objects, QueryablePropertiesManagerMixin)

        manager = QueryablePropertiesManagerMixin.apply_to(ApplicationTag.objects)
        assert manager is not ApplicationTag.objects
        assert isinstance(manager, QueryablePropertiesManagerMixin)
        assert manager.model is ApplicationTag
        assert manager._db == ApplicationTag.objects._db
        assert getattr(manager, '_hints', None) == getattr(ApplicationTag.objects, '_hints', None)
        assert manager.name == '<{}_with_queryable_properties>'.format(
            getattr(ApplicationTag.objects, 'name', 'manager'))

        queryset = manager.all()
        assert isinstance(queryset, QueryablePropertiesQuerySetMixin)
        assert set(queryset.filter(applications__version_count=4)) == set(tags)


class TestQueryablePropertiesManager:

    @pytest.mark.parametrize('using, hints', [
        (None, None),
        (None, {}),
        ('default', None),
        ('default', {'test': 'hint'}),
    ])
    def test_get_for_model(self, tags, using, hints):
        assert not isinstance(ApplicationTag._default_manager, QueryablePropertiesManagerMixin)

        manager = QueryablePropertiesManager.get_for_model(ApplicationTag, using, hints)
        assert isinstance(manager, QueryablePropertiesManagerMixin)
        assert manager.model is ApplicationTag
        assert manager._db == using
        assert manager._hints == (hints or {})
        assert manager.name == '<manager_with_queryable_properties>'

        queryset = manager.all()
        assert isinstance(queryset, QueryablePropertiesQuerySetMixin)
        assert set(queryset.filter(applications__version_count=4)) == set(tags)


class TestLegacyIterable:

    def test_initializer(self):
        queryset = ApplicationWithClassBasedProperties.objects.all()
        iterable = LegacyIterable(queryset)
        assert iterable.queryset is queryset

    def test_iter(self):
        for queryset in (
            ApplicationWithClassBasedProperties.objects.order_by('pk'),
            ApplicationWithClassBasedProperties.objects.order_by('pk').values('pk', 'name'),
            ApplicationWithClassBasedProperties.objects.order_by('pk').values_list('pk', 'name'),
            VersionWithClassBasedProperties.objects.dates('supported_from', 'year'),
        ):
            iterable = LegacyIterable(queryset)
            assert list(iterable) == list(queryset)


class TestQueryablePropertiesIterableMixin:

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


class TestLegacyOrderingModelIterable:

    @pytest.mark.parametrize('select', [
        (),
        ('version_count',),
        ('version_count', 'major_sum'),
    ])
    def test_postprocess_queryable_properties(self, refs, select):
        iterable = LegacyOrderingModelIterable(ApplicationWithClassBasedProperties.objects.all())
        iterable.__dict__['_order_by_select'] = {refs[prop_name] for prop_name in select}
        obj = ApplicationWithClassBasedProperties()
        setattr(obj, QUERYING_PROPERTIES_MARKER, True)
        for ref in iterable._order_by_select:
            ref.descriptor.set_cached_value(obj, 1337)
        obj = iterable._postprocess_queryable_properties(obj)
        for ref in iterable._order_by_select:
            assert not ref.descriptor.has_cached_value(obj)


class TestLegacyValuesIterable:

    @pytest.mark.parametrize('prop_names', [
        (),
        ('version_count',),
        ('version_count', 'major_sum'),
    ])
    def test_postprocess_queryable_properties(self, refs, prop_names):
        iterable = LegacyValuesIterable(ApplicationWithClassBasedProperties.objects.all())
        iterable.__dict__['_order_by_select'] = {refs[prop_name] for prop_name in prop_names}
        obj = {'name': 'My cool App', 'version_count': 4, 'major_sum': 5}
        result = iterable._postprocess_queryable_properties(dict(obj))
        assert result == {name: value for name, value in obj.items() if name not in prop_names}
