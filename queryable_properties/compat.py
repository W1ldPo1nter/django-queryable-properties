# encoding: utf-8
"""A stable import interface for Django classes that were moved in between versions and compatibility constants."""

try:  # pragma: no cover
    from contextlib import nullcontext  # noqa: F401
except ImportError:  # pragma: no cover
    from contextlib import contextmanager

    @contextmanager
    def nullcontext(enter_result=None):
        yield enter_result

import six
from django.db.models.query import QuerySet
from django.db.models.sql.query import Query

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

# A dictionary mapping names of build_filter/add_filter keyword arguments to
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

# Old Django versions (<1.9) had a method to check if filter conditions need
# to be put into the HAVING clause instead of the WHERE clause. To get
# queryable properties based on aggregates to work, these methods must be
# intercepted if present.
NEED_HAVING_METHOD_NAME = None
if hasattr(Query, 'need_having'):  # pragma: no cover
    NEED_HAVING_METHOD_NAME = 'need_having'
elif hasattr(Query, 'need_force_having'):  # pragma: no cover
    NEED_HAVING_METHOD_NAME = 'need_force_having'

# The annotation-related attributes of Query objects had "aggregate" in their
# name instead of "annotation" in old django versions (<1.8), because
# annotations were strongly tied to aggregates.
ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP = {}
ANNOTATION_SELECT_CACHE_NAME = '_annotation_select_cache'
if not hasattr(Query, 'annotation_select'):  # pragma: no cover
    ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP = {
        'add_annotation': 'add_aggregate',
        '_annotations': '_aggregates',
        'annotations': 'aggregates',
        '_annotation_select_cache': '_aggregate_select_cache',
        'annotation_select': 'aggregate_select',
        'annotation_select_mask': 'aggregate_select_mask',
        'set_annotation_mask': 'set_aggregate_mask',
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


def contains_aggregate(annotation):
    """
    Check if the given annotation contains an aggregate.

    :param annotation: The annotation to check.
    :return: True if the annotation contains an aggregate; otherwise False.
    :rtype: bool
    """
    # While annotations can mark themselves as containing an aggregate via the
    # contains_aggregate attribute in recent Django versions, this was not the
    # case in old versions. Annotations were strongly tied to aggregates in
    # these versions though, so an aggregate is always assumed in this case.
    return getattr(annotation, 'contains_aggregate', bool(ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP))


def get_related_model(model, relation_field_name):
    """
    Get the related model of the (presumed) relation field with the given name
    on the given model.

    :param type model: The model class to inspect the field on.
    :param str relation_field_name: The field name of the (presumed) relation
                                    field.
    :return: The model class reached via the relation field or None if the
             field is not actually a relation field.
    :rtype: type | None
    """
    if hasattr(model._meta, 'get_field_by_name'):  # pragma: no cover
        # Older Django versions (<1.8) only allowed to find reverse relation
        # objects as well as fields via the get_field_by_name method, which
        # doesn't exist in recent versions anymore.
        field_or_rel, _, direct, _ = model._meta.get_field_by_name(relation_field_name)
        # Unlike in recent Django versions, the reverse relation objects and
        # fields also didn't provide the same attributes, which is why they
        # need to be treated differently.
        if not direct:  # direct=False means a reverse relation object
            return field_or_rel.field.model
        return field_or_rel.rel and field_or_rel.rel.to
    return model._meta.get_field(relation_field_name).related_model
