# encoding: utf-8

import pytest

from django import VERSION as DJANGO_VERSION

from .models import ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties


if DJANGO_VERSION < (1, 8):
    from django.db.models.sql.aggregates import Aggregate
    from django.db.models.sql.query import Query


    class RawSQLAnnotation(Aggregate):
        """
        An annotation that simply adds custom SQL for Django versions < 1.8.
        Used to maintain the test setup by emulating newer ORM features via
        custom SQL.
        """

        def __init__(self, sql, output_field, contains_aggregate=False):
            self.sql = sql
            self.contains_aggregate = contains_aggregate
            self.field = output_field
            # Make sure all the regular attributes are set
            self.col = None
            self.source = None
            self.is_summary = False
            self.extra = {}
            self.lookup = 'pk'

        def as_sql(self, qn, connection):
            return self.sql, ()

        def add_to_query(self, query, alias, col, source, is_summary):
            query.aggregates[alias] = self

    @pytest.fixture(autouse=True)
    def patch_query_need_having(monkeypatch):
        """
        A fixture that monkeypatches a Query method to be able to use the
        RawSQLAnnotation without a HAVING clause being added in Django
        versions < 1.8.
        """
        original = Query.need_having

        def patched(self, obj):
            need_having = original(self, obj)
            if isinstance(need_having, RawSQLAnnotation):
                need_having = need_having.contains_aggregate
            return need_having

        monkeypatch.setattr(Query, 'need_having', patched)


@pytest.fixture
def applications():
    return [
        ApplicationWithClassBasedProperties.objects.create(name='My cool App'),
        ApplicationWithClassBasedProperties.objects.create(name='Another App'),
        ApplicationWithDecoratorBasedProperties.objects.create(name='My cool App'),
        ApplicationWithDecoratorBasedProperties.objects.create(name='Another App'),
    ]


@pytest.fixture
def versions(applications):
    objs = []
    for application in applications:
        objs.extend([
            application.versions.create(major=1, minor=2, patch=3),
            application.versions.create(major=1, minor=3, patch=0),
            application.versions.create(major=1, minor=3, patch=1),
            application.versions.create(major=2, minor=0, patch=0),
        ])
    return objs
