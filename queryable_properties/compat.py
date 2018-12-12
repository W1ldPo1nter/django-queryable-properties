# encoding: utf-8
"""A stable import interface for Django classes that were moved in between versions and compatibility constants."""

try:  # pragma: no cover
    from django.db.models.constants import LOOKUP_SEP  # noqa: F401
except ImportError:  # pragma: no cover
    from django.db.models.sql.constants import LOOKUP_SEP  # noqa: F401

try:  # pragma: no cover
    from django.db.models.query import ModelIterable  # noqa: F401
    ValuesQuerySet = None
except ImportError:  # pragma: no cover
    from django.db.models.query import ValuesQuerySet  # noqa: F401
    ModelIterable = None
