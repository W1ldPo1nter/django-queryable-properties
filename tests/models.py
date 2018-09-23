# encoding: utf-8
from django.db import models
from django.db.models.functions import Concat

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
        pass


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
        return Concat('major', models.Value('.'), 'minor', models.Value('.'), 'patch', output_field=models.CharField())

    def get_update_kwargs(self, cls, value):
        parts = value.rsplit('.', 1)
        return dict(major_minor=parts[0], patch=parts[1])


class Application(models.Model):
    name = models.CharField(max_length=255)

    class Meta:
        abstract = True


class ApplicationWithClassBasedProperty(Application):

    objects = QueryablePropertiesManager()

    dummy = DummyProperty()


class ApplicationWithDecoratorBasedProperty(Application):

    objects = QueryablePropertiesManager()


class Version(models.Model):
    major = models.IntegerField()
    minor = models.IntegerField()
    patch = models.IntegerField()

    class Meta:
        abstract = True


class VersionWithClassBasedProperties(Version):
    application = models.ForeignKey(ApplicationWithClassBasedProperty, on_delete=models.CASCADE,
                                    related_name='versions')

    objects = QueryablePropertiesManager()

    major_minor = MajorMinorVersionProperty()
    version = FullVersionProperty()


class VersionWithDecoratorBasedProperties(Version):
    application = models.ForeignKey(ApplicationWithDecoratorBasedProperty, on_delete=models.CASCADE,
                                    related_name='versions')

    objects = QueryablePropertiesManager()

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
        return Concat('major', models.Value('.'), 'minor', models.Value('.'), 'patch', output_field=models.CharField())

    @version.updater
    @classmethod
    def version(cls, value):
        parts = value.rsplit('.', 1)
        return dict(major_minor=parts[0], patch=parts[1])
