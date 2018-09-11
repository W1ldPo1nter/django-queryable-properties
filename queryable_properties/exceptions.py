# encoding: utf-8

from __future__ import unicode_literals

from django.core.exceptions import FieldDoesNotExist, FieldError


class QueryablePropertyError(FieldError):
    """Some kind of problem with a queryable property."""


class QueryablePropertyDoesNotExist(FieldDoesNotExist):
    """The requested queryable property does not exist"""
