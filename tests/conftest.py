# encoding: utf-8

import pytest

from django import VERSION as DJANGO_VERSION

from .models import (ApplicationWithClassBasedProperties, ApplicationWithDecoratorBasedProperties,
                     CategoryWithClassBasedProperties, CategoryWithDecoratorBasedProperties)


try:
    from django.db.models.expressions import RawSQL
except ImportError:
    from django.db.models.sql.aggregates import Aggregate
    from django.db.models.sql.query import Query
    from django.utils.tree import Node

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
            sql = '({})'.format(self.sql)
            if DJANGO_VERSION < (1, 6):
                # Very old Django versions expect the interpolated raw SQL
                return sql % self.params
            return sql, self.params

        def add_to_query(self, query, alias, col, source, is_summary):
            query.aggregates[alias] = self

    if DJANGO_VERSION < (1, 6):
        @pytest.fixture(autouse=True)
        def patch_query_add_filter(monkeypatch):
            """
            A fixture that monkeypatches a Query method to be able to use the
            RawSQLAnnotation without a HAVING clause being added in Django
            versions < 1.8.
            """
            original = Query.add_filter

            def patched(self, *args, **kwargs):
                # add_filter will add any filter clauses that reference an
                # aggregate to the HAVING clause (instead of WHERE). The work-
                # around therefore is to check how many HAVING items there were
                # before the add_filter call and to check all new HAVING items
                # that were added by the call. If one of them references a
                # RawSQL instance, it will be moved from HAVING to WHERE.
                having_count = len(self.having.children)
                original(self, *args, **kwargs)
                for entry in self.having.children[having_count:]:
                    if isinstance(entry[0], RawSQL):
                        self.having.children.remove(entry)
                        self.where.children.append(entry)

            monkeypatch.setattr(Query, 'add_filter', patched)

    else:
        @pytest.fixture(autouse=True)
        def patch_query_need_having(monkeypatch):
            """
            A fixture that monkeypatches a Query method to be able to use the
            RawSQLAnnotation without a HAVING clause being added in Django
            versions < 1.8.
            """
            original = Query.need_having

            def patched(self, obj):
                # need_having is supposed to return the information if the
                # a filter needs to be put in a HAVING clause (instead of
                # WHERE). If may be called with either a Q object (Node) or
                # a tuple containing the aggregate's alias as the first item.
                # The latter case can therefore easily be intercepted to check
                # if the aggregate is a RawSQL instance and then customize the
                # return value.
                if not isinstance(obj, Node) and isinstance(self.aggregates.get(obj[0], None), RawSQL):
                    return self.aggregates[obj[0]].contains_aggregate
                return original(self, obj)

            monkeypatch.setattr(Query, 'need_having', patched)


@pytest.fixture
def categories():
    return [
        CategoryWithClassBasedProperties.objects.create(name='Linux apps'),
        CategoryWithClassBasedProperties.objects.create(name='Windows apps'),
        CategoryWithDecoratorBasedProperties.objects.create(name='Linux apps'),
        CategoryWithDecoratorBasedProperties.objects.create(name='Windows apps'),
    ]


@pytest.fixture
def applications(categories):
    apps = [
        ApplicationWithClassBasedProperties.objects.create(name='My cool App'),
        ApplicationWithClassBasedProperties.objects.create(name='Another App'),
        ApplicationWithDecoratorBasedProperties.objects.create(name='My cool App'),
        ApplicationWithDecoratorBasedProperties.objects.create(name='Another App'),
    ]
    apps[0].categories.add(categories[0])
    apps[1].categories.add(categories[0])
    apps[1].categories.add(categories[1])
    apps[2].categories.add(categories[2])
    apps[3].categories.add(categories[2])
    apps[3].categories.add(categories[3])
    return apps


@pytest.fixture
def versions(applications):
    objs = []
    for application in applications:
        objs.extend([
            application.versions.create(major=1, minor=2, patch=3),
            application.versions.create(major=1, minor=3, patch=0),
            application.versions.create(major=1, minor=3, patch=1),
            application.versions.create(major=2, minor=0, patch=0, changes='Amazing new features'),
        ])
    return objs
