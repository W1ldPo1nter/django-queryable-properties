# encoding: utf-8
from django.db import models
try:
    from django.db.models.functions import Concat
except ImportError:
    Concat = None

from queryable_properties import AnnotationMixin, QueryableProperty, queryable_property, SetterMixin, UpdateMixin
from queryable_properties.managers import QueryablePropertiesManager


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
        queryset = queryset.order_by('-major', '-minor', '-patch').values('version')
        if not hasattr(models, 'Subquery'):
            # Emulate the subquery via custom SQL, but let Django still generate most of the SQL
            from .conftest import RawSQL
            # Random filter value that will be replaced with the reference to the outer table
            queryset = queryset.filter(application_id=1)[:1]
            filter_value = '"{table}"."{field}"'.format(table=cls._meta.db_table, field=cls._meta.pk.name)
            sql, params = queryset.query.sql_with_params()
            # The filter placeholder should always be the last one -> replace with reference to the outer table
            sql = filter_value.join(sql.rsplit('%s', 1))
            return RawSQL(sql, list(params)[:-1], output_field=models.CharField())
        return models.Subquery(queryset.filter(application=models.OuterRef('pk'))[:1], output_field=models.CharField())


class VersionCountProperty(AnnotationMixin, QueryableProperty):

    def get_value(self, obj):
        return obj.versions.count()

    def get_annotation(self, cls):
        return models.Count('versions')


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


class FullVersionProperty(UpdateMixin, AnnotationMixin, SetterMixin, QueryableProperty):

    filter_requires_annotation = False

    def get_value(self, obj):
        return '{major_minor}.{patch}'.format(major_minor=obj.major_minor, patch=obj.patch)

    def set_value(self, obj, value):
        obj.major, obj.minor, obj.patch = value.split('.')

    def get_filter(self, cls, lookup, value):
        if lookup != 'exact':
            raise NotImplementedError()
        parts = value.rsplit('.', 1)
        return models.Q(major_minor=parts[0], patch=parts[1])

    def get_annotation(self, cls):
        if Concat is None:
            from .conftest import RawSQL
            sql = '"{table}"."major" || \'.\' || "{table}"."minor" || \'.\' || "{table}"."patch"'.format(
                table=cls._meta.db_table)
            return RawSQL(sql, (), output_field=models.CharField())
        return Concat('major', models.Value('.'), 'minor', models.Value('.'), 'patch', output_field=models.CharField())

    def get_update_kwargs(self, cls, value):
        parts = value.rsplit('.', 1)
        return dict(major_minor=parts[0], patch=parts[1])


class Application(models.Model):
    name = models.CharField(max_length=255)

    class Meta:
        abstract = True


class ApplicationWithClassBasedProperties(Application):

    objects = QueryablePropertiesManager()

    highest_version = HighestVersionProperty()
    version_count = VersionCountProperty()
    dummy = DummyProperty()

    class Meta:
        verbose_name = 'Application'


class ApplicationWithDecoratorBasedProperties(Application):

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
        queryset = queryset.order_by('-major', '-minor', '-patch').values('version')
        if not hasattr(models, 'Subquery'):
            # Emulate the subquery via custom SQL, but let Django still generate most of the SQL
            from .conftest import RawSQL
            # Random filter value that will be replaced with the reference to the outer table
            queryset = queryset.filter(application_id=1)[:1]
            filter_value = '"{table}"."{field}"'.format(table=cls._meta.db_table, field=cls._meta.pk.name)
            sql, params = queryset.query.sql_with_params()
            # The filter placeholder should always be the last one -> replace with reference to the outer table
            sql = filter_value.join(sql.rsplit('%s', 1))
            return RawSQL(sql, list(params)[:-1], output_field=models.CharField())
        return models.Subquery(queryset.filter(application=models.OuterRef('pk'))[:1], output_field=models.CharField())

    @queryable_property
    def version_count(self):
        return self.versions.count()

    @version_count.annotater
    @classmethod
    def version_count(cls):
        return models.Count('versions')


class Version(models.Model):
    major = models.IntegerField()
    minor = models.IntegerField()
    patch = models.IntegerField()

    class Meta:
        abstract = True


class VersionWithClassBasedProperties(Version):
    application = models.ForeignKey(ApplicationWithClassBasedProperties, on_delete=models.CASCADE,
                                    related_name='versions')

    objects = QueryablePropertiesManager()

    major_minor = MajorMinorVersionProperty()
    version = FullVersionProperty()

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

    @version.filter(requires_annotation=False)
    @classmethod
    def version(cls, lookup, value):
        if lookup != 'exact':
            raise NotImplementedError()
        parts = value.rsplit('.', 1)
        return models.Q(major_minor=parts[0], patch=parts[1])

    @version.annotater
    @classmethod
    def version(cls):
        if Concat is None:
            from .conftest import RawSQL
            sql = '"{table}"."major" || \'.\' || "{table}"."minor" || \'.\' || "{table}"."patch"'.format(
                table=cls._meta.db_table)
            return RawSQL(sql, (), output_field=models.CharField())
        return Concat('major', models.Value('.'), 'minor', models.Value('.'), 'patch', output_field=models.CharField())

    @version.updater
    @classmethod
    def version(cls, value):
        parts = value.rsplit('.', 1)
        return dict(major_minor=parts[0], patch=parts[1])
