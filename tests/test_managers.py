# encoding: utf-8

import pytest
from django import VERSION as DJANGO_VERSION
from mock import Mock, patch
from six.moves import cPickle

from queryable_properties.compat import LOOKUP_SEP, ModelIterable
from queryable_properties.managers import (LegacyIterable, LegacyOrderingMixin, LegacyOrderingModelIterable,
                                           QueryablePropertiesIterableMixin)
from queryable_properties.utils import get_queryable_property
from queryable_properties.utils.internal import QueryPath, QueryablePropertyReference
from .app_management.models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                                    VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('versions')]


class DummyIterable(QueryablePropertiesIterableMixin, ModelIterable or LegacyBaseIterable):
    pass


class DummyOrderingIterable(LegacyOrderingMixin, LegacyBaseIterable):
    pass


@pytest.fixture
def refs():
    model = ApplicationWithClassBasedProperties
    return {
        prop_name: QueryablePropertyReference(get_queryable_property(model, prop_name), model, QueryPath())
        for prop_name in ('major_sum', 'version_count')
    }


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

    @pytest.mark.parametrize('aliases, select, expected_result', [
        ((), (), set()),
        (('version_count',), (), set()),
        (('version_count',), ('version_count',), {'version_count__'}),
        (('major_sum', 'version_count'), ('major_sum',), {'major_sum__'}),
    ])
    def test_discarded_attr_names(self, refs, aliases, select, expected_result):
        queryset = ApplicationWithClassBasedProperties.objects.all()
        iterable = LegacyOrderingModelIterable(queryset)
        iterable.__dict__['_order_by_select'] = {refs[prop_name] for prop_name in select}
        iterable.__dict__['_queryable_property_aliases'] = {
            refs[prop_name]: ''.join((prop_name, LOOKUP_SEP)) for prop_name in aliases
        }
        assert iterable._discarded_attr_names == expected_result
        for prop_name in select:
            assert refs[prop_name] not in iterable._queryable_property_aliases

    @pytest.mark.skipif(DJANGO_VERSION >= (1, 8), reason='order_by was a list in old Django versions.')
    @pytest.mark.parametrize('order_by, expected_order_by', [
        ((), []),
        (('name', '-pk'), ['name', '-pk']),
        (('version_count', '-pk'), ['version_count__', '-pk']),
        (('name', '-major_sum'), ['name', '-major_sum__']),
        (('major_sum', '-version_count', 'name', '-major_sum'),
         ['major_sum__', '-version_count__', 'name', '-major_sum__']),
    ])
    def test_setup_queryable_properties(self, order_by, expected_order_by):
        queryset = ApplicationWithClassBasedProperties.objects.order_by(*order_by)
        iterable = LegacyOrderingModelIterable(queryset)
        iterable._setup_queryable_properties()
        query = iterable.queryset.query
        assert list(query.order_by) == expected_order_by

    @pytest.mark.parametrize('discarded_names', [
        set(),
        {'version_count__'},
        {'version_count__', 'major_sum__'},
    ])
    def test_postprocess_queryable_properties(self, discarded_names):
        iterable = LegacyOrderingModelIterable(ApplicationWithClassBasedProperties.objects.all())
        iterable.__dict__['_discarded_attr_names'] = discarded_names
        obj = ApplicationWithClassBasedProperties()
        for name in discarded_names:
            setattr(obj, name, 1337)
        obj = iterable._postprocess_queryable_properties(obj)
        for name in discarded_names:
            assert not hasattr(obj, name)
