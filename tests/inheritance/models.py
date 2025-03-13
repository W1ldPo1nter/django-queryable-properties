# -*- coding: utf-8 -*-
import six
from django import VERSION as DJANGO_VERSION
from django.db import models

from queryable_properties.managers import QueryablePropertiesManager
from queryable_properties.properties import InheritanceModelProperty


class Abstract(models.Model):
    abstract_field = models.CharField(max_length=100, default='abstract_field')

    objects = QueryablePropertiesManager()

    plural = InheritanceModelProperty(lambda cls: six.text_type(cls._meta.verbose_name_plural), models.CharField())


class Parent(Abstract):
    parent_field = models.CharField(max_length=100, default='parent_field')

    if DJANGO_VERSION < (2, 0):
        objects = QueryablePropertiesManager()


class Child1(Parent):
    child1_field = models.CharField(max_length=100, default='child1_field')

    if DJANGO_VERSION < (2, 0):
        objects = QueryablePropertiesManager()


class Child2(Parent):
    child2_field = models.CharField(max_length=100, default='child2_field')

    if DJANGO_VERSION < (2, 0):
        objects = QueryablePropertiesManager()


class ProxyChild(Child1):
    class Meta:
        proxy = True


class Grandchild1(Child1):
    grandchild1_field = models.CharField(max_length=100, default='grandchild1_field')

    if DJANGO_VERSION < (2, 0):
        objects = QueryablePropertiesManager()


class DisconnectedGrandchild2(Child2):
    parent_link = models.OneToOneField(Child2, on_delete=models.CASCADE, parent_link=True, related_name='+')
    grandchild2_field = models.CharField(max_length=100, default='grandchild2_field')

    if DJANGO_VERSION < (2, 0):
        objects = QueryablePropertiesManager()


class MultipleParent1(models.Model):
    id1 = models.AutoField(primary_key=True)
    multiple_parent1_field = models.CharField(max_length=100, default='multiple_parent1_field')

    objects = QueryablePropertiesManager()

    plural = InheritanceModelProperty(lambda cls: six.text_type(cls._meta.verbose_name_plural), models.CharField())


class MultipleParent2(models.Model):
    id2 = models.AutoField(primary_key=True)
    multiple_parent2_field = models.CharField(max_length=100, default='multiple_parent2_field')


class MultipleChild(MultipleParent1, MultipleParent2):
    multiple_child_field = models.CharField(max_length=100, default='multiple_child_field')

    if DJANGO_VERSION < (2, 0):
        objects = QueryablePropertiesManager()
