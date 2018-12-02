# encoding: utf-8

from __future__ import unicode_literals

from django.core.exceptions import FieldError
try:  # pragma: no cover
    from django.core.exceptions import FieldDoesNotExist
except ImportError:  # pragma: no cover
    from django.db.models.fields import FieldDoesNotExist


class QueryablePropertyError(FieldError):
    """Some kind of problem with a queryable property."""


class QueryablePropertyDoesNotExist(FieldDoesNotExist):
    """The requested queryable property does not exist."""
