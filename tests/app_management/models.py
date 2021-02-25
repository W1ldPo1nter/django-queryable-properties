# encoding: utf-8

from datetime import date

from django import VERSION as DJANGO_VERSION
from django.db import models

from queryable_properties.managers import QueryablePropertiesManager
from queryable_properties.properties import (
    AggregateProperty, AnnotationGetterMixin, AnnotationMixin, AnnotationProperty, LookupFilterMixin, QueryableProperty,
    queryable_property, RangeCheckProperty, RelatedExistenceCheckProperty, SetterMixin, UpdateMixin, ValueCheckProperty
)
from ..dummy_lib.models import ReleaseTypeModel


class DummyProperty(SetterMixin, QueryableProperty):

    def __init__(self):
        super(DummyProperty, self).__init__()
        self.counter = 0

    def get_value(self, obj):
        self.counter += 1
        return self.counter

    def set_value(self, obj, value):
        return -1  # A value < 0 to test the CACHE_RETURN_VALUE setter behavior


class HighestVersionProperty(AnnotationMixin, QueryableProperty):

    def get_value(self, obj):
        try:
            return obj.versions.order_by('-major', '-minor', '-patch')[0].version
        except IndexError:
            return None

    def get_annotation(self, cls):
        queryset = VersionWithClassBasedProperties.objects.select_properties('version')
        queryset = queryset.filter(application=models.OuterRef('pk')).order_by('-major', '-minor', '-patch')
        return models.Subquery(queryset.values('version')[:1], output_field=models.CharField())


class VersionCountProperty(AnnotationGetterMixin, QueryableProperty):

    def get_annotation(self, cls):
        return models.Count('versions')


class LoweredVersionChangesProperty(AnnotationMixin, QueryableProperty):

    def get_annotation(self, cls):
        from django.db.models.functions import Lower
        return Lower('versions__changes_or_default')


class MajorMinorVersionProperty(UpdateMixin, QueryableProperty):

    def get_value(self, obj):
        return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)

    def get_filter(self, cls, lookup, value):
        if lookup != 'exact':
            raise NotImplementedError()
        parts = value.split('.')
        return models.Q(major=parts[0], minor=parts[1])

    def get_update_kwargs(self, cls, value):
        parts = value.split('.')
        return dict(major=parts[0], minor=parts[1])


class FullVersionProperty(LookupFilterMixin, UpdateMixin, AnnotationMixin, SetterMixin, QueryableProperty):

    filter_requires_annotation = False

    def get_value(self, obj):
        return '{major_minor}.{patch}'.format(major_minor=obj.major_minor, patch=obj.patch)

    def set_value(self, obj, value):
        obj.major, obj.minor, obj.patch = value.split('.')

    @LookupFilterMixin.lookup_filter('exact')
    def exact_filter(self, cls, lookup, value):
        parts = value.rsplit('.', 1)
        return models.Q(major_minor=parts[0], patch=parts[1])

    def get_annotation(self, cls):
        from django.db.models.functions import Concat
        return Concat('major', models.Value('.'), 'minor', models.Value('.'), 'patch', output_field=models.CharField())

    def get_update_kwargs(self, cls, value):
        parts = value.rsplit('.', 1)
        return dict(major_minor=parts[0], patch=parts[1])


class DefaultChangesProperty(AnnotationMixin, QueryableProperty):

    def get_value(self, obj):
        return obj.changes or '(No data)'

    def get_annotation(self, cls):
        from django.db.models import Value
        from django.db.models.functions import Coalesce
        return Coalesce('changes', Value('(No data)'))


class Version2Property(LookupFilterMixin, QueryableProperty):

    def get_value(self, obj):
        return obj.major == 2

    @LookupFilterMixin.boolean_filter
    def exact_filter(self, cls):
        return models.Q(major=2)


class CircularProperty(AnnotationMixin, QueryableProperty):

    def get_annotation(self, cls):
        return models.F('circular')


class Category(models.Model):
    name = models.CharField(max_length=255)

    class Meta:
        abstract = True


class CategoryWithClassBasedProperties(Category):
    objects = QueryablePropertiesManager()

    has_versions = RelatedExistenceCheckProperty('applications__versions')
    version_count = AnnotationProperty(models.Count('applications__versions'))
    circular = CircularProperty()

    class Meta:
        verbose_name = 'Category'


class CategoryWithDecoratorBasedProperties(Category):
    objects = QueryablePropertiesManager()

    class Meta:
        verbose_name = 'Category'

    @queryable_property
    def circular(self):
        raise NotImplementedError()

    @circular.annotater
    @classmethod
    def circular(cls):
        return models.F('circular')


class Application(models.Model):
    name = models.CharField(max_length=255)
    common_data = models.IntegerField(default=0)

    class Meta:
        abstract = True


class ApplicationWithClassBasedProperties(Application):
    categories = models.ManyToManyField(CategoryWithClassBasedProperties, related_name='applications')

    objects = QueryablePropertiesManager()

    highest_version = HighestVersionProperty()
    version_count = VersionCountProperty()
    major_sum = AggregateProperty(models.Sum('versions__major'))
    if DJANGO_VERSION < (1, 8):
        support_start_date = AggregateProperty(models.Min('versions__supported_from'))
    else:
        support_start_date = AggregateProperty(models.Min('versions__supported_from',
                                                          output_field=models.DateField(null=True)))
    lowered_version_changes = LoweredVersionChangesProperty()
    has_version_with_changelog = RelatedExistenceCheckProperty('versions__changes')
    dummy = DummyProperty()

    class Meta:
        verbose_name = 'Application'


class ApplicationWithDecoratorBasedProperties(Application):
    categories = models.ManyToManyField(CategoryWithDecoratorBasedProperties, related_name='applications')

    objects = QueryablePropertiesManager()

    class Meta:
        verbose_name = 'Application'

    @queryable_property
    def highest_version(self):
        try:
            return self.versions.order_by('-major', '-minor', '-patch')[0].version
        except IndexError:
            return None

    @highest_version.annotater
    @classmethod
    def highest_version(cls):
        queryset = VersionWithDecoratorBasedProperties.objects.select_properties('version')
        queryset = queryset.filter(application=models.OuterRef('pk')).order_by('-major', '-minor', '-patch')
        return models.Subquery(queryset.values('version')[:1], output_field=models.CharField())

    @queryable_property(annotation_based=True)
    @classmethod
    def version_count(cls):
        return models.Count('versions')

    @queryable_property(annotation_based=True)
    @classmethod
    def support_start_date(cls):
        return models.Min('versions__supported_from')

    @queryable_property
    def major_sum(self):
        return self.versions.aggregate(major_sum=models.Sum('major'))['major_sum']

    @major_sum.annotater
    @classmethod
    def major_sum(cls):
        return models.Sum('versions__major')

    lowered_version_changes = queryable_property()

    @lowered_version_changes.annotater
    @classmethod
    def lowered_version_changes(cls):
        from django.db.models.functions import Lower
        return Lower('versions__changes_or_default')


class Version(ReleaseTypeModel):
    major = models.IntegerField()
    minor = models.IntegerField()
    patch = models.IntegerField()
    changes = models.TextField(null=True, blank=True)
    supported_from = models.DateField(null=True)
    supported_until = models.DateField(null=True)

    class Meta:
        abstract = True


class VersionWithClassBasedProperties(Version):
    application = models.ForeignKey(ApplicationWithClassBasedProperties, on_delete=models.CASCADE,
                                    related_name='versions')

    objects = QueryablePropertiesManager()

    major_minor = MajorMinorVersionProperty()
    version = FullVersionProperty()
    changes_or_default = DefaultChangesProperty()
    is_version_2 = Version2Property()
    shares_common_data = ValueCheckProperty('application.common_data', 0)
    released_in_2018 = ValueCheckProperty('supported_from.year', 2018)
    is_supported = RangeCheckProperty('supported_from', 'supported_until', date(2019, 1, 1), include_missing=True)
    supported_in_2018 = RangeCheckProperty('supported_from.year', 'supported_until.year', 2018, include_missing=True)

    class Meta:
        verbose_name = 'Version'


class VersionWithDecoratorBasedProperties(Version):
    application = models.ForeignKey(ApplicationWithDecoratorBasedProperties, on_delete=models.CASCADE,
                                    related_name='versions')

    objects = QueryablePropertiesManager()

    class Meta:
        verbose_name = 'Version'

    @queryable_property
    def major_minor(self):
        return '{major}.{minor}'.format(major=self.major, minor=self.minor)

    @major_minor.filter
    @classmethod
    def major_minor(cls, lookup, value):
        if lookup != 'exact':
            raise NotImplementedError()
        parts = value.split('.')
        return models.Q(major=parts[0], minor=parts[1])

    @major_minor.updater
    @classmethod
    def major_minor(cls, value):
        parts = value.split('.')
        return dict(major=parts[0], minor=parts[1])

    @queryable_property
    def version(self):
        return '{major_minor}.{patch}'.format(major_minor=self.major_minor, patch=self.patch)

    @version.setter
    def version(self, value):
        self.major, self.minor, self.patch = value.split('.')

    @version.annotater
    @classmethod
    def version(cls):
        from django.db.models.functions import Concat
        return Concat('major', models.Value('.'), 'minor', models.Value('.'), 'patch', output_field=models.CharField())

    @version.filter(requires_annotation=False, lookups=('exact',))
    @classmethod
    def version(cls, lookup, value):
        parts = value.rsplit('.', 1)
        return models.Q(major_minor=parts[0], patch=parts[1])

    @version.updater
    @classmethod
    def version(cls, value):
        parts = value.rsplit('.', 1)
        return dict(major_minor=parts[0], patch=parts[1])

    @queryable_property
    def changes_or_default(self):
        return self.changes or '(No data)'

    @changes_or_default.annotater
    @classmethod
    def changes_or_default(cls):
        from django.db.models import Value
        from django.db.models.functions import Coalesce
        return Coalesce('changes', Value('(No data)'))

    @queryable_property
    def is_version_2(self):
        return self.major == 2

    @is_version_2.filter(boolean=True)
    @classmethod
    def is_version_2(cls):
        return models.Q(major=2)
