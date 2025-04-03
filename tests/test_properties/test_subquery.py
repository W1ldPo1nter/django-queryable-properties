# -*- coding: utf-8 -*-
import pytest
import six
from django.core.exceptions import FieldError
from django.db import models
from mock import Mock

try:
    from django.db.models.functions import Substr
except ImportError:
    Substr = Mock()

from queryable_properties.exceptions import QueryablePropertyError
from queryable_properties.properties import (
    QueryableProperty, SubqueryExistenceCheckProperty, SubqueryFieldProperty, SubqueryObjectProperty,
)
from queryable_properties.utils import get_queryable_property
from queryable_properties.utils.internal import get_queryable_property_descriptor
from ..app_management.models import (
    ApplicationWithClassBasedProperties, CategoryWithClassBasedProperties, DownloadLink,
    VersionWithClassBasedProperties,
)
from ..marks import skip_if_no_composite_pks, skip_if_no_subqueries

pytestmark = [skip_if_no_subqueries]


class TestSubqueryFieldProperty(object):

    @pytest.mark.parametrize('kwargs', [
        {
            'queryset': ApplicationWithClassBasedProperties.objects.filter(name='test'),
            'field_name': 'name',
        },
        {
            'queryset': ApplicationWithClassBasedProperties.objects.all(),
            'field_name': 'common_data',
            'output_field': models.IntegerField(),
            'cached': True,
        },
    ])
    def test_initializer(self, kwargs):
        prop = SubqueryFieldProperty(**kwargs)
        assert prop.queryset is kwargs['queryset']
        assert prop.field_name == kwargs['field_name']
        assert prop.output_field is kwargs.get('output_field')
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('field_name, expected_value', [
        ('version', '2.0.0'),
        ('major', 2),
    ])
    def test_build_subquery(self, monkeypatch, applications, field_name, expected_value):
        prop = get_queryable_property(ApplicationWithClassBasedProperties, 'highest_version')
        monkeypatch.setattr(prop, 'field_name', field_name)
        assert applications[0].highest_version == expected_value


class TestSubqueryExistenceCheckProperty(object):

    @pytest.mark.parametrize('kwargs', [
        {
            'queryset': ApplicationWithClassBasedProperties.objects.filter(name='test'),
        },
        {
            'queryset': ApplicationWithClassBasedProperties.objects.all(),
            'negated': True,
            'cached': True,
        },
    ])
    def test_initializer(self, kwargs):
        prop = SubqueryExistenceCheckProperty(**kwargs)
        assert prop.queryset is kwargs['queryset']
        assert prop.negated == kwargs.get('negated', False)
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('negated, delete_v2, expected_result', [
        (False, False, True),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ])
    def test_build_subquery(self, monkeypatch, categories, negated, delete_v2, expected_result):
        if delete_v2:
            VersionWithClassBasedProperties.objects.filter(major=2).delete()
        prop = get_queryable_property(CategoryWithClassBasedProperties, 'has_v2')
        monkeypatch.setattr(prop, 'negated', negated)
        assert categories[0].has_v2 is expected_result


class TestSubqueryObjectProperty(object):

    @pytest.fixture
    def ref(self):
        return get_queryable_property(ApplicationWithClassBasedProperties, 'highest_version_object')._resolve()[0]

    @pytest.mark.parametrize('kwargs', [
        {
            'model': ApplicationWithClassBasedProperties,
            'queryset': ApplicationWithClassBasedProperties.objects.filter(name='test'),
            'field_names': ('name', 'common_data'),
        },
        {
            'model': 'app_management.ApplicationWithClassBasedProperties',
            'queryset': ApplicationWithClassBasedProperties.objects.all(),
            'property_names': ('major_sum', 'major_avg'),
            'output_field': models.IntegerField(),
            'cached': True,
        },
    ])
    def test_initializer(self, kwargs):
        prop = SubqueryObjectProperty(**kwargs)
        assert prop.queryset is kwargs['queryset']
        assert prop.field_name is None
        assert prop.output_field is None
        assert prop.cached is kwargs.get('cached', QueryableProperty.cached)
        assert prop._descriptor is None
        assert prop._subquery_model == kwargs['model']
        assert prop._field_names == kwargs.get('field_names')
        assert prop._property_names == kwargs.get('property_names', ())
        assert prop._managed_refs == {}
        assert prop._field_aliases == {}
        assert prop._pk_field_names is None

    @pytest.mark.parametrize('subquery_model, field_names, property_names, expected_aliases', [
        (
            VersionWithClassBasedProperties,
            ['major', 'minor', 'patch', 'application'],
            [],
            {'pk': 'id', 'application': 'application_id'},
        ),
        (ApplicationWithClassBasedProperties, None, ['version_count', 'has_version_with_changelog'], {'pk': 'id'}),
        pytest.param(DownloadLink, None, ['alternative'], {'version': 'version_id'},
                     marks=[skip_if_no_composite_pks]),
        pytest.param(DownloadLink, ['url'], [], {'version': 'version_id'}, marks=[skip_if_no_composite_pks]),
    ])
    def test_finalize_setup(self, subquery_model, field_names, property_names, expected_aliases):
        model = Mock(__name__='MockModel')
        prop = SubqueryObjectProperty(subquery_model, None, field_names, property_names)
        prop.name = 'test'
        if field_names is None:
            field_names = [field.name for field in subquery_model._meta.concrete_fields]
        pk_attnames = [pk_field.attname for pk_field in
                       getattr(subquery_model._meta, 'pk_fields', [subquery_model._meta.pk])]
        all_names = set(subquery_model._meta.get_field(field_name).attname for field_name in field_names)
        all_names.update(pk_attnames)
        all_names.update(property_names)

        prop._finalize_setup(model, subquery_model)
        assert prop._subquery_model is subquery_model
        assert prop._pk_field_names == pk_attnames
        assert prop.field_name == pk_attnames[0]
        assert prop._field_aliases == expected_aliases
        assert set(prop._managed_refs) == all_names
        for name in all_names:
            managed_prop = prop._managed_refs[name].property
            assert isinstance(managed_prop, SubqueryFieldProperty)
            assert managed_prop.field_name == name
            if managed_prop is not prop:
                assert managed_prop.name == '-'.join((prop.name, name))
                assert getattr(model, managed_prop.name).prop == managed_prop

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('cached', [True, False])
    @pytest.mark.parametrize('has_version', [True, False])
    def test_getter_no_cache(self, monkeypatch, django_assert_num_queries, applications, ref, cached, has_version):
        monkeypatch.setattr(ref.property, 'cached', cached)
        application = applications[0]
        if has_version:
            version = application.versions.get(major=2)
        else:
            application.versions.all().delete()
            version = None

        for managed_ref in six.itervalues(ref.property._managed_refs):
            assert not managed_ref.descriptor.has_cached_value(application)

        with django_assert_num_queries(1):
            value = application.highest_version_object
            assert value == version
            assert ref.descriptor.has_cached_value(application) is cached
            if cached:
                assert ref.descriptor.get_cached_value(application) == version
                if version:
                    assert get_queryable_property_descriptor(VersionWithClassBasedProperties,
                                                             'version').get_cached_value(value) == version.version
            if version:
                assert value.version == version.version
                for field in VersionWithClassBasedProperties._meta.concrete_fields:
                    assert getattr(version, field.attname) == getattr(value, field.attname)
            for name, managed_ref in six.iteritems(ref.property._managed_refs):
                assert managed_ref.descriptor.has_cached_value(application) is cached
                if cached and managed_ref.property is not ref.property:
                    assert managed_ref.descriptor.get_cached_value(application) == getattr(version, name, None)

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('cached', [
        set(),
        {'major', 'minor', 'patch', 'application_id', 'version'},
    ])
    def test_cached_raw_values(self, django_assert_num_queries, applications, ref, cached):
        application = applications[0]
        version = application.versions.get(major=2)
        ref.descriptor.set_cached_value(application, version.pk)
        for name in cached:
            ref.property._managed_refs[name].descriptor.set_cached_value(application, getattr(version, name))

        with django_assert_num_queries(0):
            assert application.highest_version_object == version
            assert ref.descriptor.get_cached_value(application) == version
            for name in cached:
                assert getattr(application.highest_version_object, name) == getattr(version, name)
            deferred_fields = set(field.attname for field in VersionWithClassBasedProperties._meta.concrete_fields)
            deferred_fields.discard(ref.property.field_name)
            deferred_fields.difference_update(cached)
            assert application.highest_version_object.get_deferred_fields() == deferred_fields

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    def test_getter_cached_final_value(self, django_assert_num_queries, applications, ref):
        application = applications[0]
        version = application.versions.get(major=2)

        ref.descriptor.set_cached_value(application, version)
        with django_assert_num_queries(0):
            assert application.highest_version_object is version

        ref.descriptor.set_cached_value(application, None)
        with django_assert_num_queries(0):
            assert application.highest_version_object is None

    @skip_if_no_composite_pks
    @pytest.mark.django_db
    def test_getter_composite_pk(self, django_assert_num_queries, download_links):
        ref = get_queryable_property(download_links[0].__class__, 'alternative')._resolve()[0]

        # No cached value
        assert not ref.descriptor.has_cached_value(download_links[0])
        with django_assert_num_queries(1):
            assert download_links[0].alternative == download_links[1]
            assert 'sourceforge' in download_links[0].alternative.url
            assert ref.descriptor.get_cached_value(download_links[0]) == download_links[1]

        # Cached final value
        with django_assert_num_queries(0):
            assert download_links[0].alternative == download_links[1]

        # Cached raw PK values
        assert not ref.descriptor.has_cached_value(download_links[1])
        ref.descriptor.set_cached_value(download_links[1], download_links[0].version_id)
        ref.property._managed_refs['published_on'].descriptor.set_cached_value(download_links[1],
                                                                               download_links[0].published_on)
        with django_assert_num_queries(0):
            assert download_links[1].alternative == download_links[0]
        with django_assert_num_queries(1):
            assert 'github' in download_links[1].alternative.url

        # Partially cached raw PK values (treated as no cached value)
        assert not ref.descriptor.has_cached_value(download_links[2])
        ref.descriptor.set_cached_value(download_links[2], download_links[0].version_id)
        with django_assert_num_queries(1):
            assert download_links[2].alternative == download_links[3]
            assert download_links[2].alternative.version_id != download_links[0].version_id
            assert 'sourceforge' in download_links[2].alternative.url

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('field_name, value, expected_properties, expect_v2_match', [
        ('highest_version_object', 'pk', {'highest_version_object'}, True),
        ('highest_version_object', 'obj', {'highest_version_object'}, True),
        ('highest_version_object__gt', 'pk', {'highest_version_object'}, False),
        ('highest_version_object__pk', 'pk', {'highest_version_object'}, True),
        ('highest_version_object__pk', 'obj', {'highest_version_object'}, True),
        ('highest_version_object__pk__gt', 'obj', {'highest_version_object'}, False),
        ('highest_version_object__id', 'pk', {'highest_version_object'}, True),
        ('highest_version_object__id', 'obj', {'highest_version_object'}, True),
        ('highest_version_object__id__gt', 'obj', {'highest_version_object'}, False),
        ('highest_version_object__application', 'application_id', {'highest_version_object-application_id'}, True),
        ('highest_version_object__application_id', 'application_id', {'highest_version_object-application_id'}, True),
        ('highest_version_object__major', 2, {'highest_version_object-major'}, True),
        ('highest_version_object__major__gt', 1, {'highest_version_object-major'}, True),
        ('highest_version_object__major', 1, {'highest_version_object-major'}, False),
        ('highest_version_object__major__lt', 2, {'highest_version_object-major'}, False),
        ('highest_version_object__version', '2.0.0', {'highest_version_object-version'}, True),
        ('highest_version_object__version__iexact', '1.3.1', {'highest_version_object-version'}, False),
    ])
    def test_filter(self, categories, applications, field_name, value, expected_properties, expect_v2_match):
        applications[1].versions.filter(major=2).delete()
        expected_apps = {applications[int(not expect_v2_match)]}
        expected_categories = {categories[0]} if expect_v2_match else set(categories[:2])
        if value in ('pk', 'application_id'):
            value = applications[0].versions.values_list(value, flat=True).get(major=2)
        elif value == 'obj':
            value = applications[0].versions.get(major=2)

        for queryset, expected_results in (
            (ApplicationWithClassBasedProperties.objects.filter(**{field_name: value}), expected_apps),
            (
                CategoryWithClassBasedProperties.objects.filter(**{'applications__{}'.format(field_name): value}),
                expected_categories,
            ),
        ):
            assert {ref.property.name for ref in queryset.query._queryable_property_annotations} == expected_properties
            assert set(queryset) == expected_results

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    @pytest.mark.parametrize('select, expected_properties', [
        (('highest_version_object',), None),
        (
            ('highest_version_object__major', 'highest_version_object__minor', 'highest_version_object__version'),
            {'highest_version_object-major', 'highest_version_object-minor', 'highest_version_object-version'},
        ),
        (('highest_version_object__pk',), {'highest_version_object'}),
        (('highest_version_object__id',), {'highest_version_object'}),
        (('highest_version_object__major', 'highest_version_object'), None),
    ])
    def test_annotation_select(self, django_assert_num_queries, applications, ref, select, expected_properties):
        version = VersionWithClassBasedProperties.objects.filter(major=2)[0]
        if not expected_properties:
            expected_properties = {sub_ref.property.name for sub_ref in six.itervalues(ref.property._managed_refs)}
        queryset = ApplicationWithClassBasedProperties.objects.select_properties(*select)

        assert {r.property.name for r in queryset.query._queryable_property_annotations} == expected_properties
        with django_assert_num_queries(1):
            for application in queryset:
                if 'highest_version_object' in expected_properties:
                    assert ref.descriptor.has_cached_value(application)
                expected_properties.discard('highest_version_object')
                expected_properties.discard('highest_version_object-application_id')
                for name in expected_properties:
                    descriptor = get_queryable_property_descriptor(ApplicationWithClassBasedProperties, name)
                    assert descriptor.get_cached_value(application) == getattr(version, descriptor.prop.field_name)

    @pytest.mark.django_db
    @pytest.mark.parametrize('order_by, expected_property, expect_app2_first', [
        ('highest_version_object', 'highest_version_object', False),
        ('highest_version_object__pk', 'highest_version_object', False),
        ('-highest_version_object__id', 'highest_version_object', True),
        ('highest_version_object__application', 'highest_version_object-application_id', False),
        ('-highest_version_object__application_id', 'highest_version_object-application_id', True),
        ('highest_version_object__major', 'highest_version_object-major', True),
        ('-highest_version_object__version', 'highest_version_object-version', False),
    ])
    def test_annotation_implicit(self, applications, versions, order_by, expected_property, expect_app2_first):
        app_order_by = '{}application__{}'.format('-' if order_by.startswith('-') else '', order_by.replace('-', ''))
        versions[7].delete()
        expected_apps = [applications[1], applications[0]] if expect_app2_first else applications[:2]
        expected_versions = versions[:7]
        if expect_app2_first:
            while expected_versions[-1].application == expected_apps[0]:
                expected_versions.insert(0, expected_versions.pop())

        for queryset, expected_results in (
            (ApplicationWithClassBasedProperties.objects.order_by(order_by), expected_apps),
            (VersionWithClassBasedProperties.objects.order_by(app_order_by, 'pk'), expected_versions),
        ):
            assert {ref.property.name for ref in queryset.query._queryable_property_annotations} == {expected_property}
            assert list(queryset) == expected_results

    @pytest.mark.django_db
    @pytest.mark.parametrize('select, names, expected_values', [
        (('highest_version_object',), ('name', 'highest_version_object'), [
            ['My cool App', 'pk3'],
            ['Another App', 'pk6'],
        ]),
        (('highest_version_object',), ('name', 'highest_version_object__pk'), [
            ['My cool App', 'pk3'],
            ['Another App', 'pk6'],
        ]),
        (('highest_version_object',), ('highest_version_object__id', 'name'), [
            ['pk3', 'My cool App'],
            ['pk6', 'Another App'],
        ]),
        (('highest_version_object__pk',), ('highest_version_object__pk', 'name'), [
            ['pk3', 'My cool App'],
            ['pk6', 'Another App'],
        ]),
        (('highest_version_object__id',), ('name', 'highest_version_object__id'), [
            ['My cool App', 'pk3'],
            ['Another App', 'pk6'],
        ]),
        (('highest_version_object',), ('name', 'highest_version_object__major', 'highest_version_object__minor'), [
            ['My cool App', 2, 0],
            ['Another App', 1, 3],
        ]),
        (('highest_version_object',), ('name', 'highest_version_object__version'), [
            ['My cool App', '2.0.0'],
            ['Another App', '1.3.1'],
        ]),
        (('highest_version_object__version',), ('name', 'highest_version_object__version'), [
            ['My cool App', '2.0.0'],
            ['Another App', '1.3.1'],
        ]),
        (('highest_version_object',), ('name', Substr('highest_version_object__version', 1, 3)), [
            ['My cool App', '2.0'],
            ['Another App', '1.3'],
        ]),
        (('highest_version_object__version',), ('name', Substr('highest_version_object__version', 1, 3)), [
            ['My cool App', '2.0'],
            ['Another App', '1.3'],
        ]),
    ])
    def test_raw_values(self, applications, versions, select, names, expected_values):
        versions[7].delete()
        expressions = {}
        values_names = list(names)
        for name in names:
            if not isinstance(name, six.string_types):
                expressions['expr'] = name
                values_names.remove(name)
        for values in expected_values:
            for i, value in enumerate(values):
                if value in ('pk3', 'pk6'):
                    values[i] = versions[int(value[-1])].pk

        queryset = ApplicationWithClassBasedProperties.objects.select_properties(*select).order_by('pk')
        for result, values in zip(queryset.values(*values_names, **expressions), expected_values):
            assert result == dict(zip(values_names + (['expr'] if expressions else []), values))
        for result, values in zip(queryset.values_list(*names), expected_values):
            assert result == tuple(values)

    @pytest.mark.django_db
    @pytest.mark.usefixtures('versions')
    def test_raw_values_with_transform(self):
        # Django does not support using registered transforms on any annotation.
        with pytest.raises(FieldError):
            ApplicationWithClassBasedProperties.objects.select_properties('highest_version_object').values(
                'highest_version_object__version__length')

    @pytest.mark.django_db
    def test_no_subquery_row(self, django_assert_num_queries, applications, versions):
        applications[0].versions.all().delete()
        version_pk = versions[7].pk

        for queryset in (
            ApplicationWithClassBasedProperties.objects.filter(highest_version_object__isnull=True),
            ApplicationWithClassBasedProperties.objects.filter(highest_version_object=None),
            ApplicationWithClassBasedProperties.objects.filter(highest_version_object__pk__isnull=True),
            ApplicationWithClassBasedProperties.objects.filter(highest_version_object__id=None),
            ApplicationWithClassBasedProperties.objects.filter(highest_version_object__major__isnull=True),
            ApplicationWithClassBasedProperties.objects.filter(highest_version_object__version__isnull=True),
        ):
            assert queryset.get() == applications[0]

        with django_assert_num_queries(1):
            application = ApplicationWithClassBasedProperties.objects.select_properties('highest_version_object').get(
                highest_version_object__isnull=True)
            assert application.highest_version_object is None

        base_queryset = (
            ApplicationWithClassBasedProperties.objects.select_properties('highest_version_object').order_by('pk')
        )
        assert list(base_queryset.values('name', 'highest_version_object', 'highest_version_object__major')) == [
            {'name': 'My cool App', 'highest_version_object': None, 'highest_version_object__major': None},
            {'name': 'Another App', 'highest_version_object': version_pk, 'highest_version_object__major': 2},
        ]
        assert list(base_queryset.values_list('name', 'highest_version_object', 'highest_version_object__version')) == [
            ('My cool App', None, None),
            ('Another App', version_pk, '2.0.0'),
        ]

    @skip_if_no_composite_pks
    @pytest.mark.django_db
    def test_composite_pk_in_queries(self, django_assert_num_queries, download_links):
        model = download_links[0].__class__

        assert model.objects.get(alternative=download_links[0]) == download_links[1]
        assert (model.objects.get(alternative=(download_links[0].version_id, download_links[0].published_on)) ==
                download_links[1])
        assert not model.objects.filter(alternative=(download_links[0].version_id, 'Nowhere')).exists()
        assert set(model.objects.filter(alternative=download_links[0].version_id)) == set(download_links[:2])
        assert set(model.objects.filter(alternative__version=download_links[0].version_id)) == set(download_links[:2])
        assert (set(model.objects.filter(alternative__version_id=download_links[0].version_id)) ==
                set(download_links[:2]))
        assert model.objects.filter(alternative__published_on='GitHub').count() == 6

        for queryset, num_queries, field_names in (
            (model.objects.select_properties('alternative'), 1, ('pk', 'version_id', 'published_on', 'url')),
            (model.objects.select_properties('alternative__version', 'alternative__published_on'), 1,
             ('pk', 'version_id', 'published_on')),
            (model.objects.select_properties('alternative__version_id', 'alternative__published_on'), 1,
             ('pk', 'version_id', 'published_on')),
            (model.objects.select_properties('alternative__version'), 2, ('pk', 'version_id', 'published_on', 'url')),
        ):
            with django_assert_num_queries(num_queries):
                instance = queryset.get(pk=download_links[0].pk)
                for field_name in field_names:
                    assert getattr(instance.alternative, field_name) == getattr(download_links[1], field_name)
        with pytest.raises(QueryablePropertyError):
            model.objects.select_properties('alternative__pk')

        queryset = model.objects.filter(pk=download_links[0].pk).select_properties('alternative')
        assert queryset.values_list('alternative', flat=True).get() == download_links[1].version_id
        assert queryset.values_list('alternative__version', flat=True).get() == download_links[1].version_id
        assert queryset.values_list('alternative__version_id', flat=True).get() == download_links[1].version_id
        assert queryset.values_list('alternative__version', 'alternative__published_on').get() == (
            download_links[1].version_id, download_links[1].published_on)
        with pytest.raises(FieldError):
            queryset.values_list('alternative__pk')
