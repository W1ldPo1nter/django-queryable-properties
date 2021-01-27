# encoding: utf-8

from contextlib import contextmanager
from functools import partial

import six
from django.utils.tree import Node

from .compat import (
    ADD_Q_METHOD_NAME, ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP, BUILD_FILTER_METHOD_NAME, contains_aggregate,
    convert_build_filter_to_add_q_kwargs, LOOKUP_SEP, NEED_HAVING_METHOD_NAME, nullcontext, QUERY_CHAIN_METHOD_NAME,
    ValuesQuerySet
)
from .exceptions import QueryablePropertyError
from .utils.internal import InjectableMixin, resolve_queryable_property, TreeNodeProcessor


class QueryablePropertiesQueryMixin(InjectableMixin):
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

    def init_injected_attrs(self):
        # Stores references to queryable properties used as annotations in this
        # query.
        self._queryable_property_annotations = set()
        # A stack for queryable properties who are currently being annotated.
        # Required to correctly resolve dependencies and perform annotations.
        self._queryable_property_stack = []

    @contextmanager
    def _add_queryable_property_annotation(self, property_ref, full_group_by, select=False):
        """
        A context manager that adds a queryable property annotation to this
        query and performs management tasks around the annotation (stores the
        information if the queryable property annotation should be selected
        and populates the queryable property stack correctly). The context
        manager yields the actual resolved and applied annotation while the
        stack is still populated.

        :param property_ref: A reference containing the queryable property
                             to annotate.
        :type property_ref: queryable_properties.utils.internal.QueryablePropertyReference
        :param bool full_group_by: Signals whether to use all fields of the
                                   query for the GROUP BY clause when dealing
                                   with an aggregate-based annotation or not.
        :param bool select: Signals whether the annotation should be selected
                            or not.
        """
        if property_ref in self._queryable_property_stack:
            raise QueryablePropertyError('Queryable property "{}" has a circular dependency and requires itself.'
                                         .format(property_ref.property))

        annotation_name = property_ref.full_path
        annotation_mask = set(self.annotations) if self.annotation_select_mask is None else self.annotation_select_mask
        self._queryable_property_stack.append(property_ref)
        try:
            if property_ref not in self._queryable_property_annotations:
                self.add_annotation(property_ref.get_annotation(), alias=annotation_name, is_summary=False)
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
        if contains_aggregate(annotation):
            if full_group_by and not ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP:
                # In recent Django versions, a full GROUP BY can be achieved by
                # simply setting group_by to True.
                self.group_by = True
            else:
                if full_group_by:  # pragma: no cover
                    # In old versions, the fields must be added to the selected
                    # fields manually and set_group_by must be called after.
                    opts = self.model._meta
                    self.add_fields([f.attname for f in getattr(opts, 'concrete_fields', opts.fields)], False)
                self.set_group_by()

    def _auto_annotate(self, path, full_group_by=None):
        """
        Try to resolve the given path into a queryable property and annotate
        the property as a non-selected property (if the property wasn't added
        as an annotation already). Do nothing if the path does not match a
        queryable property.

        :param collections.Sequence path: The path to resolve (a string of
                                          Django's query expression split up
                                          by the lookup separator).
        :param bool | None full_group_by: Optional override to indicate whether
                                          or not all fields must be contained
                                          in a GROUP BY clause for aggregate
                                          annotations. If not set, it will be
                                          determined from the state of this
                                          query.
        :return: The resolved annotation or None if the path couldn't be
                 resolved.
        """
        property_ref = resolve_queryable_property(self.model, path)[0]
        if not property_ref:
            return None
        if full_group_by is None:
            full_group_by = bool(ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP) and not self.select
        with self._add_queryable_property_annotation(property_ref, full_group_by) as annotation:
            return annotation

    def _postprocess_clone(self, clone):
        """
        Postprocess a query that was the result of cloning this query. This
        ensures that the cloned query also uses this mixin and that the
        queryable property attributes are initialized correctly.

        :param django.db.models.sql.Query clone: The cloned query.
        :return: The postprocessed cloned query.
        :rtype: django.db.models.sql.Query
        """
        if not isinstance(clone, QueryablePropertiesQueryMixin):
            QueryablePropertiesQueryMixin.inject_into_object(clone)
        else:
            clone.init_injected_attrs()
        clone._queryable_property_annotations.update(self._queryable_property_annotations)
        return clone

    def add_aggregate(self, aggregate, model=None, alias=None, is_summary=False):  # pragma: no cover
        # This method is called in older versions to add an aggregate, which
        # may be based on a queryable property annotation, which in turn must
        # be auto-annotated here.
        path = tuple(aggregate.lookup.split(LOOKUP_SEP))
        if self._queryable_property_stack:
            path = self._queryable_property_stack[-1].relation_path + path
        property_annotation = self._auto_annotate(path)
        if property_annotation:
            # If it is based on a queryable property annotation, annotating the
            # current aggregate cannot be delegated to Django as it couldn't
            # deal with annotations containing the lookup separator.
            aggregate.add_to_query(self, alias, LOOKUP_SEP.join(path), property_annotation, is_summary)
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
        if BUILD_FILTER_METHOD_NAME == 'add_filter':
            # Simply use the build_filter implementation that does all the
            # heavy lifting and is aware of the different methods in different
            # versions and therefore calls the correct super methods if
            # necessary.
            return self.build_filter(*args, **kwargs)
        return super(QueryablePropertiesQueryMixin, self).add_filter(*args, **kwargs)

    def add_ordering(self, *ordering, **kwargs):
        for field_name in ordering:
            # Ordering by a queryable property via simple string values
            # requires auto-annotating here, while a queryable property used
            # in a complex ordering expression is resolved through overridden
            # query methods.
            if isinstance(field_name, six.string_types) and field_name != '?':
                if field_name.startswith('-') or field_name.startswith('+'):
                    field_name = field_name[1:]
                self._auto_annotate(field_name.split(LOOKUP_SEP))
        return super(QueryablePropertiesQueryMixin, self).add_ordering(*ordering, **kwargs)

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
            property_ref, lookups = resolve_queryable_property(self.model, arg.split(LOOKUP_SEP))

        # If no queryable property could be determined for the filter
        # expression (either because a regular/non-existent field is referenced
        # or because the expression was a special or invalid value), call
        # Django's default implementation, which may in turn raise an
        # exception. Act the same way if the current top of the stack is used
        # to avoid infinite recursions.
        if not property_ref or (self._queryable_property_stack and self._queryable_property_stack[-1] == property_ref):
            # The base method has different names in different Django versions
            # (see comment on the constant definition).
            base_method = getattr(super(QueryablePropertiesQueryMixin, self), BUILD_FILTER_METHOD_NAME)
            return base_method(filter_expr, *args, **kwargs)

        q_obj = property_ref.get_filter(lookups, value)
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
            # structure, so an _add_q call can be used to actually create the
            # return value for the current call. The (_)add_q method has
            # different names in different Django versions (see comment on the
            # constant definition).
            method = getattr(self, ADD_Q_METHOD_NAME)
            return method(q_obj, **convert_build_filter_to_add_q_kwargs(**kwargs))

    def get_aggregation(self, *args, **kwargs):
        # If the query is to be used as a pure aggregate query (which might use
        # a subquery), all queryable property annotations must be added to the
        # select mask to avoid potentially empty SELECT clauses.
        if self.annotation_select_mask is not None and self._queryable_property_annotations:
            annotation_names = (property_ref.full_path for property_ref in self._queryable_property_annotations)
            self.set_annotation_mask(self.annotation_select_mask.union(annotation_names))
        return super(QueryablePropertiesQueryMixin, self).get_aggregation(*args, **kwargs)

    def need_force_having(self, q_object):  # pragma: no cover
        # Same as need_having, but for even older versions. Simply delegate to
        # need_having, which is aware of the different methods in different
        # versions and therefore calls the correct super methods if
        # necessary.
        return self.need_having(q_object)

    def need_having(self, obj):  # pragma: no cover
        # This method is used by older Django versions to figure out if the
        # filter represented by a Q object must be put in the HAVING clause of
        # the query. Since a queryable property might add an aggregate-based
        # annotation during the actual filter application, this method must
        # return True if a filter condition contains such a property.
        def is_aggregate_property(item, ignored_refs=set()):
            path = item[0].split(LOOKUP_SEP)
            property_ref, lookups = resolve_queryable_property(self.model, path)
            if not property_ref or property_ref in ignored_refs:
                return False
            if property_ref.property.filter_requires_annotation:
                if contains_aggregate(property_ref.get_annotation()):
                    return True
                ignored_refs = ignored_refs.union((property_ref,))
            # Also check the Q object returned by the property's get_filter
            # method as it may contain references to other properties that may
            # add aggregation-based annotations.
            predicate = partial(is_aggregate_property, ignored_refs=ignored_refs)
            return TreeNodeProcessor(property_ref.get_filter(lookups, item[1])).check_leaves(predicate)

        if isinstance(obj, Node) and TreeNodeProcessor(obj).check_leaves(is_aggregate_property):
            return True
        elif not isinstance(obj, Node) and is_aggregate_property(obj):
            return True
        # The base method has different names in different Django versions (see
        # comment on the constant definition).
        base_method = getattr(super(QueryablePropertiesQueryMixin, self), NEED_HAVING_METHOD_NAME)
        return base_method(obj)

    def resolve_ref(self, name, allow_joins=True, reuse=None, summarize=False, *args, **kwargs):
        # This method is used to resolve field names in complex expressions. If
        # a queryable property is used in such an expression, it needs to be
        # auto-annotated (while taking the stack into account) and returned.
        path = tuple(name.split(LOOKUP_SEP))
        if self._queryable_property_stack:
            path = self._queryable_property_stack[-1].relation_path + path
        property_annotation = self._auto_annotate(path, full_group_by=ValuesQuerySet is not None)
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
        # This is a central method for resolving field names and joining the
        # required tables when dealing with paths that involve relations. To
        # also allow the usage of queryable properties across relations, the
        # relation path on top of the stack must be prepended to trick Django
        # into resolving correctly.
        if self._queryable_property_stack:
            names = self._queryable_property_stack[-1].relation_path + tuple(names)
        return super(QueryablePropertiesQueryMixin, self).setup_joins(names, *args, **kwargs)

    def clone(self, *args, **kwargs):
        obj = super(QueryablePropertiesQueryMixin, self).clone(*args, **kwargs)
        if QUERY_CHAIN_METHOD_NAME == 'clone':  # pragma: no cover
            obj = self._postprocess_clone(obj)
        return obj

    def chain(self, *args, **kwargs):
        obj = super(QueryablePropertiesQueryMixin, self).chain(*args, **kwargs)
        if QUERY_CHAIN_METHOD_NAME == 'chain':
            obj = self._postprocess_clone(obj)
        return obj
