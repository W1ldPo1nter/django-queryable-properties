# encoding: utf-8
"""A stable import interface for Django classes that were moved in between versions and compatibility constants."""

from django.db.models.query import QuerySet
from django.db.models.sql.query import Query
from django.utils import six

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

# A dictionary mapping names of build_filter/add_filter keyword argument to
# keyword arguments for an _add_q/add_q call. It contains kwargs names for
# all Django versions (some do not use all of these). If a keyword argument
# is not part of this dictionary, it will not be passed through.
BUILD_FILTER_TO_ADD_Q_KWARGS_MAP = {
    'can_reuse': 'used_aliases',
    'branch_negated': 'branch_negated',
    'current_negated': 'current_negated',
    'allow_joins': 'allow_joins',
    'split_subq': 'split_subq',
    'force_having': 'force_having',
}

# Very old django versions (<1.6) had different names for the methods
# containing the build_filter and _add_q logic, which are needed as the core
# for filters based on queryable properties.
BUILD_FILTER_METHOD_NAME = 'build_filter'
ADD_Q_METHOD_NAME = '_add_q'
if not hasattr(Query, 'build_filter'):  # pragma: no cover
    BUILD_FILTER_METHOD_NAME = 'add_filter'
    ADD_Q_METHOD_NAME = 'add_q'

# The annotation-related attributes of Query objects had "aggregate" in their
# name instead of "annotation" in old django versions (<1.8), because
# annotations were strongly tied to aggregates.
ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP = {}
ANNOTATION_SELECT_CACHE_NAME = '_annotation_select_cache'
if not hasattr(Query, 'annotations'):  # pragma: no cover
    ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP = {
        'add_annotation': 'add_aggregate',
        '_annotations': '_aggregates',
        'annotations': 'aggregates',
        '_annotation_select_cache': '_aggregate_select_cache',
        'annotation_select': 'aggregate_select',
    }
    ANNOTATION_SELECT_CACHE_NAME = '_aggregate_select_cache'

# Recent Django versions (>=2.0) have separate methods for cloning and chaining
# while older versions only have the clone method.
QUERYSET_CHAIN_METHOD_NAME = '_chain' if hasattr(QuerySet, '_chain') else '_clone'
QUERY_CHAIN_METHOD_NAME = 'chain' if hasattr(Query, 'chain') else 'clone'


def convert_build_filter_to_add_q_kwargs(**build_filter_kwargs):
    """
    Transform the keyword arguments of a :meth:`Query.build_filter` call into
    keyword arguments for an appropriate :meth:`Query._add_q` call (or their
    respective counterparts in older Django versions).

    :param build_filter_kwargs: The keyword arguments passed to
                                :meth:`Query.build_filter`.
    :return: The keywords argument to use for :meth:`Query._add_q`.
    :rtype: dict
    """
    return {BUILD_FILTER_TO_ADD_Q_KWARGS_MAP[key]: value for key, value in six.iteritems(build_filter_kwargs)
            if key in BUILD_FILTER_TO_ADD_Q_KWARGS_MAP}


def chain_queryset(queryset, *args, **kwargs):
    """
    Create a copy of the given queryset to chain a new queryset method call by
    calling the appropriate chain/clone method for the current Django version.

    :param QuerySet queryset: The queryset to chain.
    :param args: Positional arguments passed through to the method call.
    :param kwargs: Keyword arguments passed through to the method call.
    :return: A copy of given queryset.
    :rtype: QuerySet
    """
    method = getattr(queryset, QUERYSET_CHAIN_METHOD_NAME)
    return method(*args, **kwargs)


def chain_query(query, *args, **kwargs):
    """
    Create a copy of the given query to chain a new query method call by
    calling the appropriate chain/clone method for the current Django version.

    :param Query query: The query to chain.
    :param args: Positional arguments passed through to the method call.
    :param kwargs: Keyword arguments passed through to the method call.
    :return: A copy of given query.
    :rtype: Query
    """
    method = getattr(query, QUERY_CHAIN_METHOD_NAME)
    return method(*args, **kwargs)