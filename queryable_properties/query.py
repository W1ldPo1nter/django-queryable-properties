# encoding: utf-8

from __future__ import unicode_literals

from collections import OrderedDict
from contextlib import contextmanager

import six
from django.db.models import F
from django.utils.tree import Node

from .compat import (
    ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP, ValuesQuerySet, compat_call, compat_getattr, contains_aggregate,
    get_arg_names, nullcontext,
)
from .exceptions import QueryablePropertyError
from .utils.internal import InjectableMixin, NodeChecker, QueryPath, resolve_queryable_property

QUERYING_PROPERTIES_MARKER = '__querying_properties__'


class AggregatePropertyChecker(NodeChecker):
    """
    A specialized node checker that checks whether a node contains a reference
    to an aggregate property for the purposes of determining whether a HAVING
    clause is required.
    """

    def __init__(self):
        super(AggregatePropertyChecker, self).__init__(self.is_aggregate_property)

    def is_aggregate_property(self, item, model, ignored_refs=frozenset()):
        """
        Check if the given node item or its subnodes contain a reference to an
        aggregate property.

        :param (str, object) item: The node item consisting of path and value.
        :param model: The model class the corresponding query is performed for.
        :param ignored_refs: Queryable property references that should not be
                             checked.
        :type ignored_refs: frozenset[queryable_properties.utils.internal.QueryablePropertyReference]
        :return: True if the node or a subnode reference an aggregate property;
                 otherwise False.
        :rtype: bool
        """
        property_ref, lookups = resolve_queryable_property(model, QueryPath(item[0]))
        if not property_ref or property_ref in ignored_refs:
            return False
        if property_ref.property.filter_requires_annotation:
            if contains_aggregate(property_ref.get_annotation()):
                return True
            ignored_refs = ignored_refs.union((property_ref,))
        # Also check the Q object returned by the property's get_filter method
        # as it may contain references to other properties that may add
        # aggregation-based annotations.
        return self.check_leaves(property_ref.get_filter(lookups, item[1]), model=model, ignored_refs=ignored_refs)


aggregate_property_checker = AggregatePropertyChecker()


class QueryablePropertiesCompilerMixin(InjectableMixin):
    """
    A mixin for :class:`django.db.models.sql.compiler.SQLCompiler` objects that
    extends the original Django objects to inject the
    ``QUERYING_PROPERTIES_MARKER``.
    """

    def setup_query(self, *args, **kwargs):
        super(QueryablePropertiesCompilerMixin, self).setup_query(*args, **kwargs)
        # Add the marker to the column map while ensuring that it's the first
        # entry.
        annotation_col_map = OrderedDict()
        annotation_col_map[QUERYING_PROPERTIES_MARKER] = -1
        annotation_col_map.update(self.annotation_col_map)
        self.annotation_col_map = annotation_col_map

    def results_iter(self, *args, **kwargs):
        for row in super(QueryablePropertiesCompilerMixin, self).results_iter(*args, **kwargs):
            # Add the fixed value for the fake querying properties marker
            # annotation to each row. In recent versions, the value can simply
            # be appended since -1 can be specified as the index in the
            # annotation_col_map. In old versions, the value must be injected
            # as the first annotation value.
            addition = row.__class__((True,))
            if not ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP:
                row += addition
            else:  # pragma: no cover
                index = len(row) - len(self.query.aggregate_select) - len(self.query.related_select_cols)
                row = row[:index] + addition + row[index:]
            yield row


class QueryablePropertiesBaseQueryMixin(InjectableMixin):
    """
    Base mixin for queryable properties query mixins that covers common
    functionality for all query mixins.
    """

    def init_injected_attrs(self):
        # Stores references to queryable properties used as annotations in this
        # query.
        self._queryable_property_annotations = set()
        # A stack for queryable properties who are currently being annotated.
        # Required to correctly resolve dependencies and perform annotations.
        self._queryable_property_stack = []
        # Determines whether to inject the QUERYING_PROPERTIES_MARKER.
        self._use_querying_properties_marker = False

    def clone(self, *args, **kwargs):
        # Very old Django versions didn't have the chain method yet. Simply
        # delegate to the overridden chain in this case, which is aware of the
        # different methods in different versions and therefore calls the
        # correct super method.
        original = super(QueryablePropertiesBaseQueryMixin, self)
        if not hasattr(original, 'chain'):  # pragma: no cover
            return self.chain(*args, **kwargs)
        return original.clone(*args, **kwargs)

    def chain(self, *args, **kwargs):
        obj = compat_call(super(QueryablePropertiesBaseQueryMixin, self), ('chain', 'clone'), *args, **kwargs)
        # Ensure that the proper mixin is added to the cloned object as
        # chaining may change the clone's class.
        for mixin in QueryablePropertiesBaseQueryMixin.__subclasses__():
            if isinstance(self, mixin):
                mixin.inject_into_object(obj, 'QueryableProperties' + obj.__class__.__name__)
                break
        obj.init_injected_attrs()
        obj._queryable_property_annotations.update(self._queryable_property_annotations)
        return obj


class QueryablePropertiesQueryMixin(QueryablePropertiesBaseQueryMixin):
    """
    A mixin for :class:`django.db.models.sql.Query` objects that extends the
    original Django objects to deal with queryable properties, e.g. managing
    used properties or automatically adding required properties as annotations.
    """

    def __getattr__(self, name):  # pragma: no cover
        # Redirect some attribute accesses for older Django versions (where
        # annotations were tied to aggregations, hence "aggregation" in the
        # names instead of "annotation").
        if name in ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP:
            return getattr(self, ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP[name])
        raise AttributeError()

    def __setattr__(self, name, value):
        # See __getattr__.
        name = ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP.get(name, name)
        super(QueryablePropertiesQueryMixin, self).__setattr__(name, value)

    @contextmanager
    def _add_queryable_property_annotation(self, property_ref, full_group_by, select=False):
        """
        A context manager that adds a queryable property annotation to this
        query and performs management tasks around the annotation (stores
        whether the queryable property annotation should be selected and
        populates the queryable property stack correctly). The context manager
        yields the actual resolved and applied annotation while the stack is
        still populated.

        :param property_ref: A reference containing the queryable property
                             to annotate.
        :type property_ref: queryable_properties.utils.internal.QueryablePropertyReference
        :param bool full_group_by: Signals whether to use all fields of the
                                   query for the GROUP BY clause when dealing
                                   with an aggregate-based annotation.
        :param bool select: Signals whether the annotation should be selected.
        """
        if property_ref in self._queryable_property_stack:
            raise QueryablePropertyError('Queryable property "{}" has a circular dependency and requires itself.'
                                         .format(property_ref.property))

        annotation_name = property_ref.full_path.as_str()
        annotation_mask = set(self.annotations if self.annotation_select_mask is None else self.annotation_select_mask)
        was_present = property_ref in self._queryable_property_annotations
        was_selected = was_present and (self.annotation_select_mask is None or
                                        annotation_name in self.annotation_select_mask)

        self._queryable_property_stack.append(property_ref)
        try:
            if not was_present:
                self.add_annotation(property_ref.get_annotation(), alias=annotation_name)
                if not select:
                    self.set_annotation_mask(annotation_mask)
                self._queryable_property_annotations.add(property_ref)
            elif select and self.annotation_select_mask is not None:
                self.set_annotation_mask(annotation_mask.union((annotation_name,)))
            annotation = self.annotations[annotation_name]
            yield annotation
        finally:
            self._queryable_property_stack.pop()

        # Perform the required GROUP BY setup if the annotation contained
        # aggregates, which is normally done by QuerySet.annotate.
        if (not was_present or (select and not was_selected)) and contains_aggregate(annotation):
            if full_group_by and not ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP:
                # In recent Django versions, a full GROUP BY can be achieved by
                # simply setting group_by to True.
                self.group_by = True
            else:
                if full_group_by and self.group_by is None:  # pragma: no cover
                    # In old versions, the fields must be added to the selected
                    # fields manually and set_group_by must be called after.
                    opts = self.model._meta
                    self.add_fields([f.attname for f in compat_getattr(opts, 'concrete_fields', 'fields')], False)
                self.set_group_by()

    def _auto_annotate(self, query_path, full_group_by=None):
        """
        Try to resolve the given path into a queryable property and annotate
        the property as a non-selected property (if the property wasn't added
        as an annotation already). Do nothing if the path does not match a
        queryable property.

        :param QueryPath query_path: The query path to resolve.
        :param bool | None full_group_by: Optional override to indicate whether
                                          all fields must be contained in a
                                          ``GROUP BY`` clause for aggregate
                                          annotations. If not set, it will be
                                          determined from the state of this
                                          query.
        :return: A 2-tuple containing the resolved annotation as well as the
                 remaining lookups/transforms. The annotation will be None and
                 the remaining lookups/transforms will be an empty query path
                 if the path couldn't be resolved.
        :rtype: (django.db.models.expressions.BaseExpression | None, QueryPath)
        """
        property_ref, lookups = resolve_queryable_property(self.model, query_path)
        if not property_ref:
            return None, lookups
        if full_group_by is None:
            full_group_by = bool(ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP) and not self.select
        return property_ref.annotate_query(self, full_group_by, remaining_path=lookups)

    def add_aggregate(self, aggregate, model=None, alias=None, is_summary=False):  # pragma: no cover
        # This method is called in older versions to add an aggregate, which
        # may be based on a queryable property annotation, which in turn must
        # be auto-annotated here.
        query_path = QueryPath(aggregate.lookup)
        if self._queryable_property_stack:
            query_path = self._queryable_property_stack[-1].relation_path + query_path
        property_annotation = self._auto_annotate(query_path)[0]
        if property_annotation:
            # If it is based on a queryable property annotation, annotating the
            # current aggregate cannot be delegated to Django as it couldn't
            # deal with annotations containing the lookup separator.
            aggregate.add_to_query(self, alias, query_path.as_str(), property_annotation, is_summary)
        else:
            # The overridden method also allows to set a default value for the
            # model parameter, which will be missing if add_annotation calls are
            # redirected to add_aggregate for older Django versions.
            model = model or self.model
            super(QueryablePropertiesQueryMixin, self).add_aggregate(aggregate, model, alias, is_summary)
        if self.annotation_select_mask is not None:
            self.set_annotation_mask(self.annotation_select_mask.union((alias,)))

    def add_filter(self, *args, **kwargs):  # pragma: no cover
        # The build_filter method was called add_filter in very old Django
        # versions. Since recent versions still have an add_filter method (for
        # different purposes), the queryable properties customizations should
        # only occur in old versions.
        original = super(QueryablePropertiesQueryMixin, self)
        if not hasattr(original, 'build_filter'):
            # Simply use the build_filter implementation that does all the
            # heavy lifting and is aware of the different methods in different
            # versions and therefore calls the correct super methods if
            # necessary.
            return self.build_filter(*args, **kwargs)
        return original.add_filter(*args, **kwargs)

    def add_ordering(self, *ordering, **kwargs):
        ordering = list(ordering)
        for index, item in enumerate(ordering):
            # Ordering by a queryable property via simple string values
            # requires auto-annotating here as well as a transformation into
            # OrderBy expressions in recent Django versions as they may contain
            # the lookup separator, which will be confused for transform
            # application by Django. Queryable properties used in a complex
            # ordering expression is resolved through other overridden methods.
            if isinstance(item, six.string_types) and item != '?':
                descending = item.startswith('-')
                query_path = QueryPath(item.lstrip('-'))
                item, transforms = self._auto_annotate(query_path)
                if item and hasattr(F, 'resolve_expression'):
                    if not transforms:
                        item = F(query_path.as_str())
                    for transform in transforms:
                        item = self.try_transform(item, transform)
                    ordering[index] = item.desc() if descending else item.asc()
        return super(QueryablePropertiesQueryMixin, self).add_ordering(*ordering, **kwargs)

    @property
    def aggregate_select(self):  # pragma: no cover
        select = original = super(QueryablePropertiesQueryMixin, self).aggregate_select
        if self._use_querying_properties_marker:
            # Since old Django versions don't offer the annotation_col_map on
            # compilers, but read the annotations directly from the query, the
            # querying properties marker has to be injected here. The value for
            # the annotation will be provided via the compiler mixin.
            select = OrderedDict()
            select[QUERYING_PROPERTIES_MARKER] = None
            select.update(original)
        return select

    def build_filter(self, filter_expr, *args, **kwargs):
        # Check if the given filter expression is meant to use a queryable
        # property. Therefore, the possibility of filter_expr not being of the
        # correct type must be taken into account (a case Django would cover
        # already, but the check for queryable properties MUST run first).
        try:
            arg, value = filter_expr
        except (TypeError, ValueError):
            # Invalid value - just treat it as "no queryable property found"
            # and delegate it to Django.
            property_ref = None
        else:
            property_ref, lookups = resolve_queryable_property(self.model, QueryPath(arg))

        # If no queryable property could be determined for the filter
        # expression (either because a regular/non-existent field is referenced
        # or because the expression was a special or invalid value), call
        # Django's default implementation, which may in turn raise an
        # exception. Act the same way if the current top of the stack is used
        # to avoid infinite recursions.
        if not property_ref or (self._queryable_property_stack and self._queryable_property_stack[-1] == property_ref):
            return compat_call(
                super(QueryablePropertiesQueryMixin, self),
                ('build_filter', 'add_filter'),
                filter_expr,
                *args,
                **kwargs
            )

        # Before applying the filter implemented by the property, check if
        # the property signals the need of its own annotation to function.
        # If so, add the annotation first to avoid endless recursion, since
        # resolved filter will likely contain the same property name again.
        context = nullcontext()
        if property_ref.property.filter_requires_annotation:
            full_group_by = bool(ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP) and not self.select
            context = self._add_queryable_property_annotation(property_ref, full_group_by)

        with context:
            # Luckily, build_filter and _add_q use the same return value
            # structure, so an (_)add_q call can be used to actually create the
            # return value for the current call. (_)add_q arguments differ
            # between Django versions, so its arguments are inspected
            # dynamically to pass the given arguments through properly.
            add_q = compat_getattr(self, '_add_q', 'add_q')
            final_kwargs = {arg_name: kwargs[arg_name] for arg_name in get_arg_names(add_q)[2:] if arg_name in kwargs}
            final_kwargs.setdefault('used_aliases', kwargs.get('can_reuse'))
            return add_q(property_ref.get_filter(lookups, value), **final_kwargs)

    def get_aggregation(self, *args, **kwargs):
        # If the query is to be used as a pure aggregate query (which might use
        # a subquery), all queryable property annotations must be added to the
        # select mask to avoid potentially empty SELECT clauses.
        if self.annotation_select_mask is not None and self._queryable_property_annotations:
            annotation_names = (ref.full_path.as_str() for ref in self._queryable_property_annotations)
            self.set_annotation_mask(set(self.annotation_select_mask).union(annotation_names))
        return super(QueryablePropertiesQueryMixin, self).get_aggregation(*args, **kwargs)

    def get_compiler(self, *args, **kwargs):
        use_marker = self._use_querying_properties_marker
        self._use_querying_properties_marker = False
        compiler = super(QueryablePropertiesQueryMixin, self).get_compiler(*args, **kwargs)
        if use_marker:
            QueryablePropertiesCompilerMixin.inject_into_object(compiler)
        return compiler

    def names_to_path(self, names, *args, **kwargs):
        # This is a central method for resolving field names. To also allow the
        # use of queryable properties across relations, the relation path on
        # top of the stack must be prepended to trick Django into resolving
        # correctly.
        if self._queryable_property_stack:
            names = self._queryable_property_stack[-1].relation_path + names
        return compat_call(
            super(QueryablePropertiesQueryMixin, self),
            ('names_to_path', 'setup_joins'),
            names,
            *args,
            **kwargs
        )

    def need_force_having(self, q_object):  # pragma: no cover
        # Same as need_having, but for even older versions. Simply delegate to
        # need_having, which is aware of the different methods in different
        # versions and therefore calls the correct super method if necessary.
        return self.need_having(q_object)

    def need_having(self, obj):  # pragma: no cover
        # This method is used by older Django versions to figure out if the
        # filter represented by a Q object must be put in the HAVING clause of
        # the query. Since a queryable property might add an aggregate-based
        # annotation during the actual filter application, this method must
        # return True if a filter condition contains such a property.
        node = obj if isinstance(obj, Node) else Node([obj])
        if aggregate_property_checker.check_leaves(node, model=self.model):
            return True
        return compat_call(super(QueryablePropertiesQueryMixin, self), ('need_having', 'need_force_having'), obj)

    def resolve_ref(self, name, allow_joins=True, reuse=None, summarize=False, *args, **kwargs):
        # This method is used to resolve field names in complex expressions. If
        # a queryable property is used in such an expression, it needs to be
        # auto-annotated (while taking the stack into account) and returned.
        query_path = QueryPath(name)
        if self._queryable_property_stack:
            query_path = self._queryable_property_stack[-1].relation_path + query_path
        property_annotation = self._auto_annotate(query_path, full_group_by=ValuesQuerySet is not None)[0]
        if property_annotation:
            if summarize:
                # Outer queries for aggregations need refs to annotations of
                # the inner queries.
                from django.db.models.expressions import Ref
                return Ref(name, property_annotation)
            return property_annotation
        return super(QueryablePropertiesQueryMixin, self).resolve_ref(name, allow_joins, reuse, summarize,
                                                                      *args, **kwargs)

    def setup_joins(self, names, *args, **kwargs):
        # This method contained the logic of names_to_path in very old Django
        # versions. Simply delegate to the overridden names_to_path in this
        # case, which is aware of the different methods in different versions
        # and therefore calls the correct super method.
        original = super(QueryablePropertiesQueryMixin, self)
        if not hasattr(original, 'names_to_path'):  # pragma: no cover
            return self.names_to_path(names, *args, **kwargs)
        return original.setup_joins(names, *args, **kwargs)


class QueryablePropertiesRawQueryMixin(QueryablePropertiesBaseQueryMixin):
    """
    A mixin for :class:`django.db.models.sql.RawQuery` objects that allows to
    populate queryable properties in raw queries by using their names as column
    names.
    """

    def __iter__(self):
        # See QueryablePropertiesCompilerMixin.results_iter, but for raw
        # queries. The marker can simply be added as the first value as fields
        # are not strictly grouped like in regular queries.
        for row in super(QueryablePropertiesRawQueryMixin, self).__iter__():
            if self._use_querying_properties_marker:
                row = row.__class__((True,)) + row
            yield row

    def get_columns(self):
        # Like QueryablePropertiesCompilerMixin.setup_query, but for raw
        # queries. The marker can simply be added as the first value as fields
        # are not strictly grouped like in regular queries.
        columns = super(QueryablePropertiesRawQueryMixin, self).get_columns()
        if self._use_querying_properties_marker:
            columns.insert(0, QUERYING_PROPERTIES_MARKER)
        return columns
