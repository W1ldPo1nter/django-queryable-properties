# encoding: utf-8

from __future__ import unicode_literals

from contextlib import contextmanager
import uuid

from django.db.models import Manager
from django.db.models.constants import LOOKUP_SEP
from django.db.models.query import QuerySet
from django.utils import six
from django.utils.functional import curry

try:  # pragma: no cover
    from django.db.models.query import ModelIterable
    ValuesQuerySet = None
except ImportError:  # pragma: no cover
    from django.db.models.query import ValuesQuerySet
    ModelIterable = None

from .exceptions import QueryablePropertyDoesNotExist, QueryablePropertyError
from .utils import get_queryable_property, inject_mixin


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

    def __getattr__(self, name):  # pragma: no cover
        # Redirect some attribute accesses for older Django versions (where
        # annotations were tied to aggregations, hence "aggregation" in the
        # names instead of "annotation".
        if name == 'add_annotation':
            # The add_aggregate function also took the model as an additional
            # parameter, which will be supplied via curry.
            return curry(self.add_aggregate, model=self.model)
        if name in ('_annotations ', 'annotations', '_annotation_select_cache', 'annotation_select'):
            return getattr(self, name.replace('annotation', 'aggregate'))
        raise AttributeError()

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

    def _auto_annotate(self, path):
        """
        Try to resolve the given path into a queryable property and annotate
        the property as a non-selected property (if the property wasn't added
        as an annotation already). Do nothing if the path does not match a
        queryable property.

        :param collections.Sequence path: The path to resolve (a string of
                                          Django's query expression split up
                                          by the lookup separator).
        :return: The resolved annotation or None if the path couldn't be
                 resolved.
        """
        prop = self._resolve_queryable_property(path)
        if not prop:
            return None
        return self.add_queryable_property_annotation(prop)

    def add_queryable_property_annotation(self, prop, select=False):
        """
        Add an annotation for the given queryable property to this query (if
        it wasn't annotated already). An exception will be raised if the
        property to add does not support annotation creation.

        :param queryable_properties.properties.QueryableProperty prop:
            The property to add an annotation for.
        :param bool select: Signals whether the annotation should be selected
                            or not.
        :return: The resolved annotation.
        """
        if prop not in self._queryable_property_annotations:
            if not prop.get_annotation:
                raise QueryablePropertyError('Queryable property "{}" needs to be added as annotation but does not '
                                             'implement annotation creation.'.format(prop.name))
            self.add_annotation(prop.get_annotation(self.model), alias=prop.name, is_summary=False)
            # Perform the required GROUP BY setup if the annotation contained
            # aggregates, which is normally done by QuerySet.annotate. In older
            # Django versions, the contains_aggregate attribute didn't exist,
            # but aggregates are always assumed in this case since annotations
            # were strongly tied to aggregates.
            if getattr(self.annotations[prop.name], 'contains_aggregate', True) and self.group_by is not True:
                self.set_group_by()
        self._queryable_property_annotations[prop] = self._queryable_property_annotations.get(prop, False) or select
        return self.annotations[prop.name]

    def add_aggregate(self, aggregate, *args, **kwargs):
        # This method is called in older versions to add an aggregation or
        # annotation. Since both might be based on a queryable property, an
        # auto-annotation has to occur here.
        self._auto_annotate(aggregate.lookup.split(LOOKUP_SEP))
        return super(QueryablePropertiesQueryMixin, self).add_aggregate(aggregate, *args, **kwargs)

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

    def names_to_path(self, names, *args, **kwargs):
        # This method is called when Django tries to resolve field names. If
        # a queryable property is used, it needs to be auto-annotated and its
        # infos must be returned instead of calling Django's default
        # implementation.
        property_annotation = self._auto_annotate(names)
        if property_annotation:
            return [], property_annotation.output_field, (property_annotation.output_field,), []
        return super(QueryablePropertiesQueryMixin, self).names_to_path(names, *args, **kwargs)

    def resolve_ref(self, name, allow_joins=True, reuse=None, summarize=False):
        # This method is used to resolve field names in complex expressions. If
        # a queryable property is used in such an expression, it needs to be
        # auto-annotated and returned here.
        property_annotation = self._auto_annotate([name])
        if property_annotation:
            if summarize:
                # Outer queries for aggregations need refs to annotations of
                # the inner queries
                from django.db.models.expressions import Ref
                return Ref(name, property_annotation)
            else:
                return property_annotation
        return super(QueryablePropertiesQueryMixin, self).resolve_ref(name, allow_joins, reuse, summarize)

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

    def __init__(self, *args, **kwargs):
        super(QueryablePropertiesQuerySetMixin, self).__init__(*args, **kwargs)
        # To work correctly, a query using the QueryablePropertiesQueryMixin is
        # required. If the current query is not using the mixin already, it
        # will be dynamically injected into the query. That way, other Django
        # extensions using custom query objects are also supported.
        if not isinstance(self.query, QueryablePropertiesQueryMixin):
            self.query = getattr(self.query, 'chain', self.query.clone)()
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
        return ((ModelIterable is not None and issubclass(self._iterable_class, ModelIterable)) or  # noqa: W504
                (ValuesQuerySet is not None and not isinstance(self, ValuesQuerySet)))

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
                if additional_name in kwargs and kwargs[additional_name] != value:
                    raise QueryablePropertyError(
                        'Updating queryable property "{prop}" would change field "{field}", but a conflicting value '
                        'was set for this field by another queryable property or explicitly in the update arguments.'
                        .format(prop=original_name, field=additional_name)
                    )
                kwargs[additional_name] = value

        return kwargs

    def _change_queryable_property_aliases(self):
        """
        Change the internal aliases of the annotations that belong to queryable
        properties in the query of this queryset to something unique and return
        a dictionary mapping the queryable properties to the changed aliases.
        This is necessary to allow Django to populate the annotation attributes
        on the resulting model instances, which would otherwise call the setter
        of the queryable properties. This way, Django can populate attributes
        with different names instead and avoid using the setter methods.

        :return: A dictionary mapping the queryable properties that selected
                 annotations are based on to the changed aliases.
        :rtype: dict[queryable_properties.properties.QueryableProperty, str]
        """
        changed_aliases = {}
        select = dict(self.query.annotation_select)
        legacy_mode = '_annotation_select_cache' not in self.query.__dict__

        for prop, requires_selection in self.query._queryable_property_annotations.items():
            if prop.name not in select:
                continue  # Annotations may have been removed somehow

            # Older Django versions didn't make a clear distinction between
            # selected an non-selected annotations, therefore non-selected
            # annotations can only be removed from the annotation select dict
            # in newer versions (to no unnecessarily query fields).
            if not requires_selection and not legacy_mode:
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
            changed_aliases[prop] = changed_name
            select[changed_name] = select.pop(prop.name)

            # Older Django versions only work with the annotation select dict
            # when it comes to ordering, so queryable property annotations used
            # for ordering must be renamed in the queries ordering as well.
            if legacy_mode:  # pragma: no cover
                for i, field_name in enumerate(self.query.order_by):
                    if field_name == prop.name or field_name[1:] == prop.name:
                        self.query.order_by[i] = field_name.replace(prop.name, changed_name)

        # Patch the correct select property on the query with the new names,
        # since this property is used by the SQL compiler to build the actual
        # SQL query (which is where the the changed names should be used).
        setattr(self.query, '_aggregate_select_cache' if legacy_mode else '_annotation_select_cache', select)
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

    def order_by(self, *field_names):
        queryset = super(QueryablePropertiesQuerySetMixin, self).order_by(*field_names)
        for field_name in field_names:
            # Ordering by a queryable property via simple string values
            # requires auto-annotating here, while a queryable property used
            # in a complex ordering expression is resolved through overridden
            # query methods.
            if isinstance(field_name, six.string_types) and field_name != '?':
                if field_name.startswith('-') or field_name.startswith('+'):
                    field_name = field_name[1:]
                queryset.query._auto_annotate(field_name.split(LOOKUP_SEP))
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
            self.query = getattr(original_query, 'chain', original_query.clone)()
            changed_aliases = self._change_queryable_property_aliases()
            super_method()
        finally:
            self.query = original_query

        # Retrieve the annotation values from each renamed attribute and use it
        # to populate the cache for the corresponding queryable property on
        # each object. Remove the weird, renamed attributes afterwards.
        for prop, changed_name in six.iteritems(changed_aliases):
            for obj in self._result_cache:
                value = getattr(obj, changed_name)
                delattr(obj, changed_name)
                # The following check is only required for older Django
                # versions, where all annotations were necessarily selected.
                # Therefore values that have been selected only due to this
                # will simply be discarded.
                if self.query._queryable_property_annotations[prop]:
                    prop._set_cached_value(obj, value)


class QueryablePropertiesQuerySet(QueryablePropertiesQuerySetMixin, QuerySet):
    """
    A special queryset class that allows to use queryable properties in its
    filter conditions, annotations and update queries.
    """
    pass


if hasattr(Manager, 'from_queryset'):
    QueryablePropertiesManager = Manager.from_queryset(QueryablePropertiesQuerySet)
else:  # pragma: no cover
    class QueryablePropertiesManager(Manager):

        def get_queryset(self):
            return QueryablePropertiesQuerySet(self.model, using=self._db)

        def select_properties(self, *names):
            return self.get_queryset().select_properties(*names)
