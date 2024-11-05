"""A stable import interface for Django classes that were moved in between versions and compatibility constants."""

try:  # pragma: no cover
    # since python 3.7
    from contextlib import nullcontext  # noqa: F401
except ImportError:  # pragma: no cover
    from contextlib import contextmanager

    @contextmanager
    def nullcontext(enter_result=None):
        yield enter_result

try:  # pragma: no cover
    # since django 4.1a1
    from django.db.models.query import RawModelIterable
except ImportError:  # pragma: no cover
    RawModelIterable = None


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
    return {BUILD_FILTER_TO_ADD_Q_KWARGS_MAP[key]: value for key, value in build_filter_kwargs.items()
            if key in BUILD_FILTER_TO_ADD_Q_KWARGS_MAP}
