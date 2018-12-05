# encoding: utf-8

import pytest

from .models import ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties


try:
    from django.db.models.expressions import RawSQL
except ImportError:
    from django.db.models.sql.aggregates import Aggregate
    from django.db.models.sql.query import Query

    class RawSQL(Aggregate):
        """
        An annotation that simply adds custom SQL for Django versions < 1.8.
        Used to maintain the test setup by emulating newer ORM features via
        custom SQL.
        """

        def __init__(self, sql, params, output_field):
            self.sql = sql
            self.params = params
            self.contains_aggregate = False
            self.field = output_field
            # Make sure all the regular attributes are set
            self.col = None
            self.source = None
            self.is_summary = False
            self.extra = {}
            self.lookup = 'pk'

        def as_sql(self, qn, connection):
            return '({})'.format(self.sql), self.params

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
            if isinstance(need_having, RawSQL):
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
