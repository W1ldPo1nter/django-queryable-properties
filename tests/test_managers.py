# encoding: utf-8
import pytest

from queryable_properties.exceptions import QueryablePropertyError

from .models import VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties


@pytest.mark.django_db
class TestQueryFilters(object):

    @pytest.mark.parametrize('model, major_minor, expected_count', [
        (VersionWithClassBasedProperties, '1.2', 2),
        (VersionWithClassBasedProperties, '1.3', 4),
        (VersionWithClassBasedProperties, '2.0', 2),
        (VersionWithDecoratorBasedProperties, '1.2', 2),
        (VersionWithDecoratorBasedProperties, '1.3', 4),
        (VersionWithDecoratorBasedProperties, '2.0', 2),
    ])
    def test_simple_filter(self, versions, model, major_minor, expected_count):
        queryset = model.objects.filter(major_minor=major_minor)
        assert len(queryset) == expected_count
        assert all(obj.major_minor == major_minor for obj in queryset)

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_filter_without_required_annotation(self, versions, model):
        queryset = model.objects.filter(version='1.2.3')
        assert 'version' not in queryset.query.annotations
        assert all(obj.version == '1.2.3' for obj in queryset)


@pytest.mark.django_db
class TestQueryAnnotations(object):

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_cached_annotation_value(self, versions, model):
        queryset = model.objects.select_properties('version')
        assert 'version' in queryset.query.annotations
        assert all(model.version._has_cached_value(obj) for obj in queryset)

    @pytest.mark.parametrize('model', [VersionWithClassBasedProperties, VersionWithDecoratorBasedProperties])
    def test_exception_on_unimplemented_annotater(self, model):
        with pytest.raises(QueryablePropertyError):
            model.objects.select_properties('major_minor')
