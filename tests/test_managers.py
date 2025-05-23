# encoding: utf-8

import pytest
from django import VERSION as DJANGO_VERSION
from mock import Mock, patch
from six.moves import cPickle

from queryable_properties.compat import ModelIterable, ValuesQuerySet
from queryable_properties.managers import (
    LegacyIterable, LegacyOrderingMixin, LegacyOrderingModelIterable, LegacyValuesIterable, LegacyValuesListIterable,
    QueryablePropertiesIterableMixin, QueryablePropertiesManager, QueryablePropertiesManagerMixin,
    QueryablePropertiesQuerySet, QueryablePropertiesQuerySetMixin,
)
from queryable_properties.query import QUERYING_PROPERTIES_MARKER
from queryable_properties.utils import get_queryable_property
from .app_management.models import (
    ApplicationTag, ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
    VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties,
)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class DummyIterable(QueryablePropertiesIterableMixin, ModelIterable or LegacyIterable):
    pass


class DummyOrderingIterable(LegacyOrderingMixin, LegacyIterable):
    pass


@pytest.fixture
def refs():
    model = ApplicationWithClassBasedProperties
    return {prop_name: get_queryable_property(model, prop_name)._resolve()[0]
            for prop_name in ('major_sum', 'version_count')}


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

    @pytest.mark.skipif(DJANGO_VERSION >= (1, 9), reason="_clone doesn't change the class in recent Django versions.")
    @pytest.mark.parametrize('change_class, setup, kwargs', [
        (False, False, {}),
        (False, True, {'dummy': None}),
        (True, False, {}),
        (True, True, {'test1': 'test', 'test2': 1337}),
    ])
    def test_clone_with_class_change(self, change_class, setup, kwargs):
        queryset = ApplicationWithClassBasedProperties.objects.all()
        assert isinstance(queryset, QueryablePropertiesQuerySetMixin)
        cls = ValuesQuerySet if change_class else None
        clone = queryset._clone(cls, setup, _fields=[], **kwargs)
        assert isinstance(clone, ValuesQuerySet) is change_class
        for name, value in kwargs.items():
            assert getattr(clone, name) == value

    def test_apply_to(self, tags):
        queryset_without_properties = ApplicationTag.objects.all()
        assert not isinstance(queryset_without_properties, QueryablePropertiesQuerySetMixin)

        queryset = QueryablePropertiesQuerySetMixin.apply_to(queryset_without_properties)
        assert queryset is not queryset_without_properties
        assert isinstance(queryset, QueryablePropertiesQuerySetMixin)
        assert list(queryset_without_properties) == list(queryset)
        assert set(queryset.filter(applications__version_count=4)) == set(tags)


class TestQueryablePropertiesQuerySet(object):

    def test_get_for_model(self, tags):
        queryset_without_properties = ApplicationTag._default_manager.all()
        assert not isinstance(queryset_without_properties, QueryablePropertiesQuerySetMixin)

        queryset = QueryablePropertiesQuerySet.get_for_model(ApplicationTag)
        assert isinstance(queryset, QueryablePropertiesQuerySetMixin)
        assert list(queryset_without_properties) == list(queryset)
        assert set(queryset.filter(applications__version_count=4)) == set(tags)


class TestQueryablePropertiesManagerMixin(object):

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


class TestQueryablePropertiesManager(object):

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


class TestLegacyIterable(object):

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


@pytest.mark.skipif(DJANGO_VERSION >= (1, 8), reason='Legacy ordering only affects very old Django versions.')
class TestLegacyOrderingMixin(object):

    @pytest.mark.parametrize('order_by, expected_indexes', [
        ((), {}),
        (('name', '-pk'), {}),
        (('version_count', '-pk'), {'version_count': [0]}),
        (('name', '-major_sum'), {'major_sum': [1]}),
        (('major_sum', '-version_count', 'name', '-major_sum'), {'major_sum': [0, 3], 'version_count': [1]}),
    ])
    def test_order_by_occurrences(self, order_by, expected_indexes):
        queryset = ApplicationWithClassBasedProperties.objects.order_by(*order_by)
        iterable = DummyOrderingIterable(queryset)
        assert len(iterable._order_by_occurrences) == len(expected_indexes)
        for ref, indexes in iterable._order_by_occurrences.items():
            assert expected_indexes[ref.property.name] == indexes

    @pytest.mark.parametrize('order_by, select, expected_result', [
        ((), (), set()),
        (('name', '-pk'), (), set()),
        (('version_count', '-pk'), (), {'version_count'}),
        (('name', '-major_sum'), ('major_sum',), set()),
        (('major_sum', '-version_count', 'name', '-major_sum'), (), {'major_sum', 'version_count'}),
        (('major_sum', '-version_count', 'name', '-major_sum'), ('version_count',), {'major_sum'}),
        (('major_sum', '-version_count', 'name', '-major_sum'), ('version_count', 'major_sum'), set()),
    ])
    def test_order_by_select(self, order_by, select, expected_result):
        queryset = ApplicationWithClassBasedProperties.objects.select_properties(*select).order_by(*order_by)
        iterable = DummyOrderingIterable(queryset)
        assert {ref.property.name for ref in iterable._order_by_select} == expected_result

    @pytest.mark.parametrize('order_by_select', [
        (),
        ('version_count',),
        ('major_sum', 'version_count'),
    ])
    def test_setup_queryable_properties(self, refs, order_by_select):
        queryset = ApplicationWithClassBasedProperties.objects.order_by('-major_sum', 'version_count')
        iterable = DummyOrderingIterable(queryset)
        iterable.__dict__['_order_by_select'] = {refs[prop_name] for prop_name in order_by_select}
        iterable._setup_queryable_properties()
        query = iterable.queryset.query
        for prop_name in ('major_sum', 'version_count'):
            if prop_name in order_by_select:
                assert query.annotation_select[prop_name] == query.annotations[prop_name]
            else:
                assert prop_name not in query.annotation_select


class TestLegacyOrderingModelIterable(object):

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


class TestLegacyValuesIterable(object):

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


@pytest.mark.skipif(DJANGO_VERSION >= (1, 8), reason='ValuesListQuerySets only exist in old Django versions.')
class TestLegacyValuesListIterable(object):

    @pytest.mark.parametrize('flat', [True, False])
    def test_initializer(self, flat):
        queryset = ApplicationWithClassBasedProperties.objects.values_list('name', flat=flat)
        iterable = LegacyValuesListIterable(queryset)
        assert iterable.queryset.flat is False
        assert iterable.flat is flat

    @pytest.mark.parametrize('select, values, expected_indexes', [
        ((), (), {-1, -2}),
        ((), ('name', 'common_data'), {-1, -2}),
        (('version_count',), (), 'major_sum'),
        (('version_count',), ('version_count', 'name'), {-1}),
        (('major_sum', 'version_count'), (), set()),
        (('major_sum', 'version_count'), ('name',), {-1, -2}),
        (('major_sum', 'version_count'), ('version_count', 'name'), {-1}),
    ])
    def test_discarded_indexes(self, select, values, expected_indexes):
        queryset = ApplicationWithClassBasedProperties.objects.select_properties(*select)
        iterable = LegacyValuesListIterable(queryset.order_by('major_sum', 'version_count').values_list(*values))
        iterable._setup_queryable_properties()
        if not isinstance(expected_indexes, set):
            expected_indexes = {list(iterable.queryset.query.aggregate_select).index(expected_indexes) - 2}
        assert iterable._discarded_indexes == expected_indexes

    @pytest.mark.parametrize('discarded_indexes, expected_result', [
        (set(), tuple(range(10))),
        ({-1}, tuple(range(9))),
        ({-2}, (0, 1, 2, 3, 4, 5, 6, 7, 9)),
        ({-1, -2, -5}, (0, 1, 2, 3, 4, 6, 7)),
    ])
    def test_postprocess_queryable_properties(self, discarded_indexes, expected_result):
        queryset = ApplicationWithClassBasedProperties.objects.values_list('name')
        iterable = LegacyValuesListIterable(queryset)
        iterable.__dict__['_discarded_indexes'] = discarded_indexes
        obj = tuple(range(10))
        assert iterable._postprocess_queryable_properties(obj) == expected_result
