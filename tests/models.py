# encoding: utf-8

from datetime import date

from django.db import models

from queryable_properties.managers import QueryablePropertiesManager
from queryable_properties.properties import (AnnotationMixin, LookupFilterMixin, QueryableProperty, queryable_property,
                                             RangeCheckProperty, SetterMixin, UpdateMixin, ValueCheckProperty)


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


class VersionCountProperty(AnnotationMixin, QueryableProperty):

    def get_value(self, obj):
        return obj.versions.count()

    def get_annotation(self, cls):
        return models.Count('versions')


class MajorSumProperty(AnnotationMixin, QueryableProperty):

    def get_value(self, obj):
        return obj.versions.aggregate(major_sum=models.Sum('major'))['major_sum'] or 0

    def get_annotation(self, cls):
        return models.Sum('versions__major')


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
    major_sum = MajorSumProperty()
    lowered_version_changes = LoweredVersionChangesProperty()
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

    @queryable_property
    def version_count(self):
        return self.versions.count()

    @version_count.annotater
    @classmethod
    def version_count(cls):
        return models.Count('versions')

    @queryable_property
    def major_sum(self):
        return self.versions.aggregate(major_sum=models.Sum('major'))['major_sum'] or 0

    @major_sum.annotater
    @classmethod
    def major_sum(cls):
        return models.Sum('versions__major')

    @queryable_property
    def lowered_version_changes(self):
        raise NotImplementedError()

    @lowered_version_changes.annotater
    @classmethod
    def lowered_version_changes(cls):
        from django.db.models.functions import Lower
        return Lower('versions__changes_or_default')


class Version(models.Model):
    ALPHA = 'a'
    BETA = 'b'
    STABLE = 's'
    RELEASE_TYPE_CHOICES = (
        (ALPHA, 'Alpha'),
        (BETA, 'Beta'),
        (STABLE, 'Stable'),
    )

    major = models.IntegerField()
    minor = models.IntegerField()
    patch = models.IntegerField()
    changes = models.TextField(null=True, blank=True)
    release_type = models.CharField(max_length=1, choices=RELEASE_TYPE_CHOICES, default=STABLE)
    supported_from = models.DateField()
    supported_until = models.DateField()

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
    is_alpha = ValueCheckProperty('release_type', Version.ALPHA)
    is_beta = ValueCheckProperty('release_type', Version.BETA)
    is_stable = ValueCheckProperty('release_type', Version.STABLE)
    is_unstable = ValueCheckProperty('release_type', Version.ALPHA, Version.BETA)
    is_supported = RangeCheckProperty('supported_from', 'supported_until', date(2019, 1, 1))

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
