# encoding: utf-8

import pytest

from django import VERSION as DJANGO_VERSION
from django.db import models

from queryable_properties.exceptions import FieldError, QueryablePropertyError

from ..models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                      CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties,
                      VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties)

pytestmark = pytest.mark.django_db


class TestFilter(object):

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_exception_on_unimplemented_filter(self, monkeypatch, model):
        monkeypatch.setattr(model.version, 'get_filter', None)
        with pytest.raises(QueryablePropertyError):
            model.objects.filter(version='1.2.3')

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_standard_exception_on_invalid_field_name(self, model):
        with pytest.raises(FieldError):
            model.objects.filter(non_existent_field=1337)

    @pytest.mark.skipif(DJANGO_VERSION < (1, 9), reason="type check didn't exist before Django 1.9")
    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_standard_exception_on_invalid_filter_expression(self, model):
        with pytest.raises(FieldError):
            # The dict is passed as arg instead of kwargs, making it an invalid
            # filter expression.
            model.objects.filter(models.Q({'version': '2.0.0'}))


class TestAnnotation(object):

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_exception_on_unimplemented_annotater(self, model):
        with pytest.raises(QueryablePropertyError):
            model.objects.select_properties('major_minor')

    @pytest.mark.skipif(DJANGO_VERSION < (1, 8), reason="Expression-based annotations didn't exist before Django 1.8")
    @pytest.mark.parametrize('model', [CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties])
    def test_circular_property(self, model):
        with pytest.raises(QueryablePropertyError, match='circular dependency'):
            model.objects.filter(circular=1337)
        with pytest.raises(QueryablePropertyError, match='circular dependency'):
            model.objects.select_properties('circular')


class TestUpdate(object):

    @pytest.mark.parametrize('model', [ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties])
    def test_exception_on_unimplemented_updater(self, model):
        with pytest.raises(QueryablePropertyError):
            model.objects.update(highest_version='1.3.37')

    @pytest.mark.parametrize('model, kwargs', [
        (VersionWithClassBasedProperties, {'major_minor': '42.42', 'major': 18}),
        (VersionWithClassBasedProperties, {'major_minor': '1.2', 'version': '1.3.37', 'minor': 5}),
        (VersionWithDecoratorBasedProperties, {'major_minor': '42.42', 'major': 18}),
        (VersionWithDecoratorBasedProperties, {'major_minor': '1.2', 'version': '1.3.37', 'minor': 5}),
    ])
    def test_exception_on_conflicting_values(self, model, kwargs):
        with pytest.raises(QueryablePropertyError):
            model.objects.update(**kwargs)


class TestOrdering(object):

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_exception_on_unimplemented_annotater(self, model):
        with pytest.raises(QueryablePropertyError):
            iter(model.objects.order_by('major_minor'))
