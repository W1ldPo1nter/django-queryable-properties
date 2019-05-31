# encoding: utf-8

from collections import namedtuple
from contextlib import contextmanager

from .compat import (ADD_Q_METHOD_NAME, ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP, BUILD_FILTER_METHOD_NAME,
                     convert_build_filter_to_add_q_kwargs, dummy_context, get_related_model, LOOKUP_SEP, Ref)
from .exceptions import FieldDoesNotExist, QueryablePropertyDoesNotExist, QueryablePropertyError
from .utils import get_queryable_property, InjectableMixin, modify_tree_node


class QueryablePropertyReference(namedtuple('QueryablePropertyReference', 'property model relation_path')):
    """
    A reference to a queryable property that also holds the path to reach the
    property across relations.
    """
    __slots__ = ()

    @property
    def full_path(self):
        """
        Return the full path to the queryable property (including the relation
        prefix) in the query filter format.

        :return: The full path to the queryable property.
        :rtype: str
        """
        if not self.relation_path:
            return self.property.name
        return LOOKUP_SEP.join(self.relation_path + (self.property.name,))

    def get_filter(self, lookup, value):
        """
        A wrapper for the get_filter method of the property this reference
        points to. It checks if the property actually supports filtering and
        applies the relation path (if any) to the returned Q object.

        :param str lookup: The lookup to use for the filter (e.g. 'exact',
                           'lt', etc.)
        :param value: The value passed to the filter condition.
        :return: A Q object to filter using this property.
        :rtype: django.db.models.Q
        """
        if not self.property.get_filter:
            raise QueryablePropertyError('Queryable property "{}" is supposed to be used as a filter but does not '
                                         'implement filtering.'.format(self.property.name))

        # Use the model stored on this reference instead of the one on the
        # property since the query may be happening from a subclass of the
        # model the property is defined on.
        q_obj = self.property.get_filter(self.model, lookup, value)
        if self.relation_path:
            # If the resolved property belongs to a related model, all actual
            # conditions in the returned Q object must be modified to use the
            # current relation path as prefix.
            q_obj = modify_tree_node(q_obj, lambda item: (LOOKUP_SEP.join(self.relation_path + (item[0],)), item[1]))
        return q_obj

    def get_annotation(self):
        """
        A wrapper for the get_annotation method of the property this reference
        points to. It checks if the property actually supports annotation
        creation performs the internal call with the correct model class.

        :return: An annotation object.
        """
        if not self.property.get_annotation:
            raise QueryablePropertyError('Queryable property "{}" needs to be added as annotation but does not '
                                         'implement annotation creation.'.format(self.property.name))
        # Use the model stored on this reference instead of the one on the
        # property since the query may be happening from a subclass of the
        # model the property is defined on.
        return self.property.get_annotation(self.model)


class QueryablePropertiesQueryMixin(InjectableMixin):
    """
    A mixin for :class:`django.db.models.sql.Query` objects that extends the
    original Django objects to deal with queryable properties, e.g. managing
    used properties or automatically add required properties as annotations.
    """

    def __getattr__(self, name):  # pragma: no cover
        # Redirect some attribute accesses for older Django versions (where
        # annotations were tied to aggregations, hence "aggregation" in the
        # names instead of "annotation").
        if name in ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP:
            return getattr(self, ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP[name])
        raise AttributeError()

    def init_injected_attrs(self):
        # Stores queryable properties used as annotations in this query along
        # with the information if the annotated value should be selected.
        self._queryable_property_annotations = {}
        # A stack for queryable properties who are currently being annotated.
        # Required to correctly resolve dependencies and perform annotations.
        self._queryable_property_stack = []

    def _resolve_queryable_property(self, path):
        """
        Resolve the given path into a queryable property on the model
        associated with this query.

        :param collections.Sequence[str] path: The path to resolve (a string of
                                               Django's query expression split
                                               up by the lookup separator).
        :return: A 2-tuple containing a queryable property reference for the
                 resolved property and a list containing the parts of the path
                 that represent lookups (or transforms). The first item will be
                 None and the list will be empty if no queryable property could
                 be resolved.
        :rtype: (QueryablePropertyReference, list[str])
        """
        model = self.model
        property_ref, lookups = None, []
        # Try to follow the given path to allow to use queryable properties
        # across relations.
        for index, name in enumerate(path):
            try:
                related_model = get_related_model(model, name)
            except FieldDoesNotExist:
                try:
                    prop = get_queryable_property(model, name)
                except QueryablePropertyDoesNotExist:
                    # Neither a field nor a queryable property, so likely an
                    # invalid name. Do nothing and let Django deal with it.
                    pass
                else:
                    property_ref = QueryablePropertyReference(prop, model, tuple(path[:index]))
                    lookups = path[index + 1:]
                # The current name was not a field and either a queryable
                # property or invalid. Either way, resolving ends here.
                break
            else:
                if not related_model:
                    # A regular model field that doesn't represent a relation,
                    # meaning that no queryable property is involved.
                    break
                model = related_model
        return property_ref, lookups

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
        property_ref = self._resolve_queryable_property(path)[0]
        if not property_ref:
            return None
        with self.add_queryable_property_annotation(property_ref) as annotation:
            return annotation

    @contextmanager
    def add_queryable_property_annotation(self, property_ref, select=False):
        """
        A context manager that adds a queryable property annotation to this
        query and performs management tasks around the annotation (stores the
        information if the queryable property annotation should be selected
        and populates the queryable property stack correctly). The context
        manager yields the actual resolved and applied annotation while the
        stack is still populated.

        :param QueryablePropertyReference property_ref: A reference containing
                                                        the queryable property
                                                        to annotate.
        :param bool select: Signals whether the annotation should be selected
                            or not.
        """
        if property_ref in self._queryable_property_stack:
            raise QueryablePropertyError('Queryable property "{}" has a circular dependency and requires itself.'
                                         .format(property_ref.property.name))

        self._queryable_property_stack.append(property_ref)
        try:
            if property_ref not in self._queryable_property_annotations:
                self.add_annotation(property_ref.get_annotation(), alias=property_ref.full_path, is_summary=False)
                # Perform the required GROUP BY setup if the annotation contained
                # aggregates, which is normally done by QuerySet.annotate. In older
                # Django versions, the contains_aggregate attribute didn't exist,
                # but aggregates are always assumed in this case since annotations
                # were strongly tied to aggregates.
                if (getattr(self.annotations[property_ref.full_path], 'contains_aggregate', True) and
                        self.group_by is not True):
                    self.set_group_by()
            else:
                select = select or self._queryable_property_annotations[property_ref]
            self._queryable_property_annotations[property_ref] = select
            yield self.annotations[property_ref.full_path]
        finally:
            self._queryable_property_stack.pop()

    def add_aggregate(self, aggregate, model=None, alias=None, is_summary=False):  # pragma: no cover
        # This method is called in older versions to add an aggregation or
        # annotation. Since both might be based on a queryable property, an
        # auto-annotation has to occur here.
        path = tuple(aggregate.lookup.split(LOOKUP_SEP))
        if self._queryable_property_stack:
            path = self._queryable_property_stack[-1].relation_path + path
        self._auto_annotate(path)
        # The overridden method also allows to set a default value for the
        # model parameter, which will be missing if add_annotation calls are
        # redirected to add_aggregate for older Django versions.
        model = model or self.model
        return super(QueryablePropertiesQueryMixin, self).add_aggregate(aggregate, model, alias, is_summary)

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

    def build_filter(self, filter_expr, *args, **kwargs):
        # Check if the given filter expression is meant to use a queryable
        # property. Therefore, the possibility of filter_expr not being of the
        # correct type must be taken into account (a case Django would cover
        # already, but the check for queryable properties MUST run first).
        try:
            arg, value = filter_expr
        except ValueError:
            # Invalid value - just treat it as "no queryable property found",
            # delegate it to Django and let it generate the exception.
            property_ref = None
        else:
            property_ref, lookups = self._resolve_queryable_property(arg.split(LOOKUP_SEP))

        # If no queryable property could be determined for the filter
        # expression (either because a regular/non-existent field is referenced
        # or because the expression was an invalid value), call Django's
        # default implementation, which may in turn raise an exception. Act the
        # same way if the current top of the stack is used to avoid infinite
        # recursions.
        if not property_ref or (self._queryable_property_stack and self._queryable_property_stack[-1] == property_ref):
            # The base method has different names in different Django versions
            # (see comment on the constant definition).
            base_method = getattr(super(QueryablePropertiesQueryMixin, self), BUILD_FILTER_METHOD_NAME)
            return base_method(filter_expr, *args, **kwargs)

        lookup = LOOKUP_SEP.join(lookups) if lookups else 'exact'
        q_obj = property_ref.get_filter(lookup, value)

        # Before applying the filter implemented by the property, check if
        # the property signals the need of its own annotation to function.
        # If so, add the annotation first to avoid endless recursion, since
        # resolved filter will likely contain the same property name again.
        context = dummy_context()
        if property_ref.property.filter_requires_annotation:
            context = self.add_queryable_property_annotation(property_ref)

        with context:
            # Luckily, build_filter and _add_q use the same return value
            # structure, so an _add_q call can be used to actually create the
            # return value for the current call. The (_)add_q method has
            # different names in different Django versions (see comment on the
            # constant definition).
            method = getattr(self, ADD_Q_METHOD_NAME)
            return method(q_obj, **convert_build_filter_to_add_q_kwargs(**kwargs))

    def resolve_ref(self, name, allow_joins=True, reuse=None, summarize=False, *args, **kwargs):
        # This method is used to resolve field names in complex expressions. If
        # a queryable property is used in such an expression, it needs to be
        # auto-annotated (while taking the stack into account) and returned.
        path = tuple(name.split(LOOKUP_SEP))
        if self._queryable_property_stack:
            path = self._queryable_property_stack[-1].relation_path + path
        property_annotation = self._auto_annotate(path)
        if property_annotation:
            if summarize:
                # Outer queries for aggregations need refs to annotations of
                # the inner queries.
                return Ref(name, property_annotation)
            return property_annotation
        return super(QueryablePropertiesQueryMixin, self).resolve_ref(name, allow_joins, reuse, summarize,
                                                                      *args, **kwargs)

    def set_group_by(self, *args, **kwargs):
        # This method is just to set up the fields that must be included in a
        # GROUP BY clause. If it is called while a related queryable property
        # is on top of the stack, the PK field of the model the property is
        # defined on must be added to those fields to ensure that aggregates
        # are applied to the correct records.
        super(QueryablePropertiesQueryMixin, self).set_group_by(*args, **kwargs)
        if self._queryable_property_stack and self._queryable_property_stack[-1].relation_path:
            # Recent Django versions have objects to represent references to
            # columns, while older versions express this via tuples/strings.
            if Ref is not None:
                group_by = self.resolve_ref('pk')
            else:
                opts = self._queryable_property_stack[-1].model._meta
                group_by = (opts.db_table, opts.pk.column)
            self.group_by += (group_by,)

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
        if not isinstance(obj, QueryablePropertiesQueryMixin):  # pragma: no cover
            QueryablePropertiesQueryMixin.inject_into_object(obj)
        else:
            obj.init_injected_attrs()
        obj._queryable_property_annotations.update(self._queryable_property_annotations)
        return obj
