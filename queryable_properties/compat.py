# encoding: utf-8
"""
A stable import interface for Python/Django entities across versions as well as compatibility constants and functions.
"""

from copy import deepcopy
from operator import attrgetter

try:  # pragma: no cover
    from contextlib import nullcontext  # noqa: F401
except ImportError:  # pragma: no cover
    from contextlib import contextmanager

    @contextmanager
    def nullcontext(enter_result=None):
        yield enter_result

try:  # pragma: no cover
    from inspect import getfullargspec
except ImportError:  # pragma: no cover
    from inspect import getargspec as getfullargspec

from django.db.models.sql.query import Query

try:  # pragma: no cover
    from django.contrib.admin import validation as admin_validation  # noqa: F401
except ImportError:  # pragma: no cover
    admin_validation = None  # noqa: F401

try:  # pragma: no cover
    from django.core import checks  # noqa: F401
except ImportError:  # pragma: no cover
    checks = None  # noqa: F401

try:  # pragma: no cover
    from django.db.models.constants import LOOKUP_SEP  # noqa: F401
except ImportError:  # pragma: no cover
    from django.db.models.sql.constants import LOOKUP_SEP  # noqa: F401

try:  # pragma: no cover
    from django.db.models.query import ModelIterable  # noqa: F401
    ValuesListQuerySet = ValuesQuerySet = None
except ImportError:  # pragma: no cover
    from django.db.models.query import ValuesListQuerySet, ValuesQuerySet  # noqa: F401
    ModelIterable = None

try:  # pragma: no cover
    from django.db.models.query import RawModelIterable  # noqa: F401
except ImportError:  # pragma: no cover
    RawModelIterable = None  # noqa: F401

try:  # pragma: no cover
    from django.db.models.query import DateQuerySet  # noqa: F401
except ImportError:  # pragma: no cover
    DateQuerySet = None  # noqa: F401

try:  # pragma: no cover
    from django.db.models.query import DateTimeQuerySet  # noqa: F401
except ImportError:  # pragma: no cover
    DateTimeQuerySet = None  # noqa: F401

try:  # pragma: no cover
    from django.forms.utils import pretty_name  # noqa: F401
except ImportError:  # pragma: no cover
    from django.forms.forms import pretty_name  # noqa: F401

# The annotation-related attributes of Query objects had "aggregate" in their
# name instead of "annotation" in old django versions (<1.8), because
# annotations were strongly tied to aggregates.
ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP = {}
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


def compat_getattr(obj, *attr_names):
    """
    Get an attribute value from an object while taking multiple attributes into account to allow compatibility with
    multiple Python/Django versions.

    :param obj: The object to get the attribute value from.
    :param str attr_names: The attribute names to take into account in the given order. Names may use dot notation.
    :return: The attribute value, taken from the first attribute in `attr_names` that exists on the given object.
    """
    for attr_name in attr_names:
        try:
            return attrgetter(attr_name)(obj)
        except AttributeError:
            continue
    raise AttributeError()


def compat_setattr(obj, value, *attr_names):
    """
    Set an attribute value on an object while taking multiple attributes into account to allow compatibility with
    multiple Python/Django versions.

    :param obj: The object to set the attribute value on.
    :param value: The value to set.
    :param str attr_names: The attribute names to take into account in the given order. The first attribute that exists
                           will be set.
    """
    for attr_name in attr_names:
        if hasattr(obj, attr_name):
            setattr(obj, attr_name, value)
            return
    raise AttributeError()


def compat_call(obj, method_names, *args, **kwargs):
    """
    Perform a method call on an object while taking multiple methods into account to allow compatibility with multiple
    Python/Django versions.

    :param obj: The object to call the method on.
    :param collections.Sequence[str] method_names: The method names to take into account in the given order.
    :return: The return value of the call of the first method that exists.
    """
    method = compat_getattr(obj, *method_names)
    return method(*args, **kwargs)


def get_arg_names(func):
    """
    Get a list of all non-variadic argument names (including keyword-only arguments in newer Python versions) of the
    given function.

    :param function func: The function to get the argument names from.
    :return: The argument names of all non-variadic arguments.
    :rtype: list[str]
    """
    spec = getfullargspec(func)
    return spec.args + getattr(spec, 'kwonlyargs', [])


def chain_queryset(queryset, *args, **kwargs):
    """
    Create a copy of the given queryset to chain a new queryset method call by
    calling the appropriate chain/clone method for the current Django version.

    :param django.db.models.query.QuerySet queryset: The queryset to chain.
    :param args: Positional arguments passed through to the method call.
    :param kwargs: Keyword arguments passed through to the method call.
    :return: A copy of given queryset.
    :rtype: django.db.models.query.QuerySet
    """
    if hasattr(queryset, '_chain'):
        return queryset._chain(*args, **kwargs)
    if hasattr(queryset, '_clone'):
        return queryset._clone(*args, **kwargs)
    return deepcopy(queryset)  # pragma: no cover


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
        field_or_rel, direct = model._meta.get_field_by_name(relation_field_name)[::2]
        # Unlike in recent Django versions, the reverse relation objects and
        # fields also didn't provide the same attributes, which is why they
        # need to be treated differently.
        if not direct:  # direct=False means a reverse relation object
            return field_or_rel.field.model
        return field_or_rel.rel and field_or_rel.rel.to
    return model._meta.get_field(relation_field_name).related_model
