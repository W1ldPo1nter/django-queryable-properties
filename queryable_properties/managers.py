# encoding: utf-8

from __future__ import unicode_literals

from contextlib import contextmanager
import uuid

from django.db.models import F, Manager, QuerySet
from django.db.models.constants import LOOKUP_SEP
from django.db.models.query import ModelIterable
from django.utils import six

from .exceptions import QueryablePropertyDoesNotExist, QueryablePropertyError
from .utils import get_queryable_property, inject_mixin


# TODO: Make properties usable across relations, auto-annotate in order_by
class QueryablePropertiesQueryMixin(object):
    """
    A mixin for :class:`django.db.models.sql.Query` objects that extends the
    original Django objects to deal with queryable properties, e.g. managing
    used properties or automatically add required properties as annotations.
    """

    BUILD_FILTER_TO_ADD_Q_KWARGS_MAP = {
        'can_reuse': 'used_aliases',
        'branch_negated': 'branch_negated',
        'current_negated': 'current_negated',
        'allow_joins': 'allow_joins',
        'split_subq': 'split_subq',
    }

    def __init__(self, *args, **kwargs):
        super(QueryablePropertiesQueryMixin, self).__init__(*args, **kwargs)
        # Stores queryable properties used as annotations in this query along
        # with the information if the annotated value should be selected.
        self._queryable_property_annotations = {}
        # A stack for queryable properties whose annotations are currently
        # required while filtering.
        self._required_annotation_stack = []

    @contextmanager
    def _required_annotation(self, prop=None):
        """
        Context manager to add the given queryable property to the top of the
        required annotation stack when entering and removing it again when
        exiting. Intended to be used when queryable properties with
        filter_requires_annotation=True are used to filter. The given property
        may be None (which won't change the stack at all) to simplify any code
        using the context manager.

        :param queryable_properties.properties.QueryableProperty prop:
            The property that should act as the current context.
        """
        if prop:
            self._required_annotation_stack.append(prop)
        yield self
        if prop:
            self._required_annotation_stack.pop()

    def _resolve_queryable_property(self, path):
        """
        Resolve the given path into a queryable property on the model
        associated with this query.

        :param collections.Sequence path: The path to resolve (a string of
                                          Django's query expression split up
                                          by the lookup separator).
        :return: The queryable property (if one could be resolved) or None.
        :rtype: queryable_properties.properties.QueryableProperty | None
        """
        try:
            prop = get_queryable_property(self.model, path[0])
        except QueryablePropertyDoesNotExist:
            return None

        # Currently, only properties defined directly at the model associated
        # with this query are supported.
        if len(path) > 2:
            raise QueryablePropertyError('Cannot resolve queryable property filter "{}". It may only consist of '
                                         'the property name and a single lookup.'.format(path))
        return prop

    def _build_filter_to_add_q_kwargs(self, **build_filter_kwargs):
        """
        Transform the keyword arguments of a :meth:`build_filter` call into
        keyword arguments for an appropriate :meth:`_add_q` call.

        :param build_filter_kwargs: The keyword arguments passed to
                                    :meth:`build_filter`.
        :return: The keywords argument to use for :meth:`_add_q`.
        :rtype: dict
        """
        add_q_kwargs = {}
        for key, value in six.iteritems(build_filter_kwargs):
            if key in self.BUILD_FILTER_TO_ADD_Q_KWARGS_MAP:
                add_q_kwargs[self.BUILD_FILTER_TO_ADD_Q_KWARGS_MAP[key]] = value
        return add_q_kwargs

    def add_queryable_property_annotation(self, prop, select=False):
        """
        Add an annotation for the given queryable property to this query (if
        it wasn't annotated already). An exception will be raised if the
        property to add does not support annotation creation.

        :param queryable_properties.properties.QueryableProperty prop:
            The property to add an annotation for.
        :param bool select: Signals whether the annotation should be selected
                            or not.
        """
        if prop not in self._queryable_property_annotations:
            if not prop.get_annotation:
                raise QueryablePropertyError('Queryable property "{}" needs to be added as annotation but does not '
                                             'implement annotation creation.'.format(prop.name))
            self.add_annotation(prop.get_annotation(self.model), prop.name)
            # Perform the requires GROUP BY setup if the annotation contained
            # aggregates, which is normally done by QuerySet.annotate.
            if self.annotations[prop.name].contains_aggregate and self.group_by is not True:
                self.set_group_by()
        self._queryable_property_annotations[prop] = self._queryable_property_annotations.get(prop, False) or select

    def build_filter(self, filter_expr, **kwargs):
        # Check if the given filter expression is meant to use a queryable
        # property. Therefore, the possibility of filter_expr not being of the
        # correct type must be taken into account (a case Django would cover
        # already, but the check for queryable properties MUST run first).
        try:
            arg, value = filter_expr
        except ValueError:
            # Invalid value - just treat it as "no queryable property found",
            # delegate it to Django and let it generate the exception.
            path = prop = None
        else:
            path = arg.split(LOOKUP_SEP)
            prop = self._resolve_queryable_property(path)

        if not prop or (self._required_annotation_stack and self._required_annotation_stack[-1] == prop):
            # If no queryable property could be determined for the filter
            # expression (either because a regular/non-existent field is
            # referenced or because the expression was an invalid value),
            # call Django's default implementation, which may in turn raise an
            # exception. Act the same way if the current top of the required
            # annotation stack is used to avoid endless recursions.
            return super(QueryablePropertiesQueryMixin, self).build_filter(filter_expr, **kwargs)

        if not prop.get_filter:
            raise QueryablePropertyError('Queryable property "{}" is supposed to be used as a filter but does not '
                                         'implement filtering.'.format(prop.name))

        # Before applying the filter implemented by the property, check if
        # the property signals the need of its own annotation to function.
        # If so, add the annotation first to avoid endless recursion, since
        # resolved filter will likely contain the same property name again.
        required_annotation_prop = None
        if prop.filter_requires_annotation:
            self.add_queryable_property_annotation(prop)
            required_annotation_prop = prop
        lookup = path[1] if len(path) > 1 else 'exact'
        q_object = prop.get_filter(self.model, lookup, value)
        # Luckily, build_filter and _add_q use the same return value
        # structure, so an _add_q call can be used to actually create the
        # return value for the current call.
        with self._required_annotation(required_annotation_prop):
            return self._add_q(q_object, **self._build_filter_to_add_q_kwargs(**kwargs))

    def add_annotation(self, annotation, alias, is_summary=False):
        # An annotation may reference a field name that is actually a queryable
        # property, which may not have been annotated yet. If that's the case,
        # add the queryable property annotation to the query, so these kinds of
        # annotations work without explicitly adding the queryable property
        # annotations to the query first.
        if isinstance(annotation, F) and annotation.name not in self.annotations:
            prop = self._resolve_queryable_property([annotation.name])
            if prop:
                self.add_queryable_property_annotation(prop)
        return super(QueryablePropertiesQueryMixin, self).add_annotation(annotation, alias, is_summary)

    def clone(self, *args, **kwargs):
        obj = super(QueryablePropertiesQueryMixin, self).clone(*args, **kwargs)
        obj._queryable_property_annotations = dict(self._queryable_property_annotations)
        obj._required_annotation_stack = list(self._required_annotation_stack)
        return obj


class QueryablePropertiesQuerySetMixin(object):
    """
    A mixin for Django's :class:`django.db.models.QuerySet` objects that allows
    to use queryable properties in filters, annotations and update queries.
    """

    def __init__(self, model=None, query=None, using=None, hints=None):
        super(QueryablePropertiesQuerySetMixin, self).__init__(model, query, using, hints)
        # To work correctly, a query using the QueryablePropertiesQueryMixin is
        # required. If the current query is not using the mixin already, it
        # will be dynamically injected into the query. That way, other Django
        # extensions using custom query objects are also supported.
        if not isinstance(self.query, QueryablePropertiesQueryMixin):
            self.query = self.query.clone()
            class_name = 'QueryableProperties' + self.query.__class__.__name__
            inject_mixin(self.query, QueryablePropertiesQueryMixin, class_name,
                         _queryable_property_annotations={}, _required_annotation_stack=[])

    @property
    def _returns_model_instances(self):
        """
        Determine if this queryset returns actual model instances or other data
        structures like tuples or dictionaries via e.g. :meth:`values_list` or
        :meth:`values`.

        :return: True if model instances are returned; otherwise False.
        :rtype: bool
        """
        return issubclass(self._iterable_class, ModelIterable)

    def _resolve_update_kwargs(self, **kwargs):
        """
        Look for the names of queryable properties in the given keyword
        arguments for an update query and correctly resolve them into their
        actual keyword arguments.

        :param kwargs: Keyword arguments of an update query.
        :return: A dictionary containing the resolved arguments.
        :rtype: dict
        """
        original_names = set(kwargs)
        for original_name in original_names:
            try:
                prop = get_queryable_property(self.model, original_name)
            except QueryablePropertyDoesNotExist:
                continue
            if not prop.get_update_kwargs:
                raise QueryablePropertyError('Queryable property "{}" does not implement queryset updating.'
                                             .format(original_name))

            # Call the method recursively since queryable properties can build
            # upon each other.
            additional_kwargs = self._resolve_update_kwargs(
                **prop.get_update_kwargs(self.model, kwargs.pop(original_name)))
            # Make sure that there are no conflicting values after resolving
            # the update keyword arguments of the queryable properties.
            for additional_name, value in six.iteritems(additional_kwargs):
                if additional_name in kwargs:
                    raise QueryablePropertyError(
                        'Updating queryable property "{prop}" would change field "{field}", but a conflicting explicit '
                        'value was set for this field in the update arguments.'
                        .format(prop=original_name, field=additional_name)
                    )
                kwargs[additional_name] = value

        return kwargs

    def _change_queryable_property_aliases(self):
        """
        Change the internal aliases of the annotations that belong to queryable
        properties in the query of this queryset to something unique and return
        a dictionary mapping the original annotation names to the changed ones.
        This is necessary to allow Django to populate the annotation attributes
        on the resulting model instances, which would otherwise call the setter
        of the queryable properties. This way, Django can populate attributes
        with different names instead and avoid using the setter methods.

        :return: A dictionary mapping the original annotation names to the
                 changed ones.
        :rtype: dict
        """
        changed_aliases = {}
        select = dict(self.query.annotation_select)
        for prop, requires_selection in dict(self.query._queryable_property_annotations).items():
            if prop.name not in select or not requires_selection:
                # Annotations may have been removed somehow or don't require
                # selection
                del self.query._queryable_property_annotations[prop]
                select.pop(prop.name, None)
                continue

            changed_name = prop.name
            # Suffix the original annotation names with random UUIDs until an
            # available name could be found. Since the suffix is delimited by
            # the lookup separator, these names are guaranteed to not clash
            # with names of model fields, which don't allow the separator in
            # their names.
            while changed_name in select:
                changed_name = LOOKUP_SEP.join((prop.name, uuid.uuid4().hex))
            changed_aliases[prop.name] = changed_name
            select[changed_name] = select.pop(prop.name)

        # Patch the correct select property on the query with the new names,
        # since this property is used by the SQL compiler to build the actual
        # SQL query (which is where the the changed names should be used).
        self.query._annotation_select_cache = select
        return changed_aliases

    def select_properties(self, *names):
        """
        Add the annotations of the queryable properties with the specified
        names to this query. The annotation values will be cached in the
        properties of resulting model instances, regardless of the regular
        caching behavior of the queried properties.

        :param names: Names of queryable properties.
        :return: A copy of this queryset with the added annotations.
        :rtype: QueryablePropertiesQuerySetMixin
        """
        queryset = getattr(self, '_chain', self._clone)()
        for name in names:
            prop = get_queryable_property(self.model, name)
            queryset.query.add_queryable_property_annotation(prop, select=True)
        return queryset

    def update(self, **kwargs):
        # Resolve any queryable properties into their actual update kwargs
        # before calling the base update method.
        kwargs = self._resolve_update_kwargs(**kwargs)
        return super(QueryablePropertiesQuerySetMixin, self).update(**kwargs)

    def _fetch_all(self):
        # Annotation caching magic happens here: If this queryset is about to
        # actually perform an SQL query (i.e. there are no cached results yet)
        # and this queryset returns model instances, the queryable property
        # annotations need to be renamed so Django doesn't call their setter.
        super_method = super(QueryablePropertiesQuerySetMixin, self)._fetch_all
        if self._result_cache is not None or not self._returns_model_instances:
            super_method()
            return

        original_query = self.query
        try:
            # Do the renaming and the actual query execution on a clone of the
            # current query object. That way, the query object can then be
            # changed back to the original one where nothing was renamed and
            # can be used for the constructions of further querysets based on
            # this one.
            self.query = original_query.clone()
            changed_aliases = self._change_queryable_property_aliases()
            super_method()
        finally:
            self.query = original_query

        # Retrieve the annotation values from each renamed attribute and use it
        # to populate the cache for the corresponding queryable property on
        # each object. Remove the weird, renamed attributes afterwards.
        for original_name, changed_name in six.iteritems(changed_aliases):
            prop = get_queryable_property(self.model, original_name)
            for obj in self._result_cache:
                prop._set_cached_value(obj, getattr(obj, changed_name))
                delattr(obj, changed_name)


class QueryablePropertiesQuerySet(QueryablePropertiesQuerySetMixin, QuerySet):
    """
    A special queryset class that allows to use queryable properties in its
    filter conditions, annotations and update queries.
    """
    pass


QueryablePropertiesManager = Manager.from_queryset(QueryablePropertiesQuerySet)
