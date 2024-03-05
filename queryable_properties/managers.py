# encoding: utf-8

from __future__ import unicode_literals

from copy import copy

import six
from django.db.models import Manager
from django.db.models.query import QuerySet
from django.utils.functional import cached_property

from .compat import (
    ANNOTATION_SELECT_CACHE_NAME, ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP, MANAGER_QUERYSET_METHOD_NAME, DateQuerySet,
    DateTimeQuerySet, ModelIterable, RawModelIterable, RawQuery, ValuesListQuerySet, ValuesQuerySet, chain_query,
    chain_queryset,
)
from .exceptions import QueryablePropertyDoesNotExist, QueryablePropertyError
from .query import QUERYING_PROPERTIES_MARKER, inject_query_mixin
from .utils import get_queryable_property
from .utils.internal import InjectableMixin, QueryablePropertyReference, QueryPath


class LegacyIterable(object):
    """
    Base class for queryset iterables for old Django versions to mimic the
    iterable classes of new Django versions.
    """

    def __init__(self, queryset):
        """
        Initialize a new legacy iterable for the given queryset.

        :param QuerySet queryset: The queryset to perform the database query
                                  for.
        """
        self.queryset = queryset

    def __iter__(self):
        original = super(QueryablePropertiesBaseQuerySetMixin, self.queryset)
        return getattr(original, 'iterator', original.__iter__)()


class QueryablePropertiesIterableMixin(object):
    """
    Base class for iterable mixins that handle queryable properties logic.

    Can be applied to both Django's iterable classes as well as the legacy
    iterable classes.
    """

    def __init__(self, queryset, *args, **kwargs):
        super(QueryablePropertiesIterableMixin, self).__init__(chain_queryset(queryset), *args, **kwargs)

    def __iter__(self):
        self._setup_queryable_properties()
        for obj in super(QueryablePropertiesIterableMixin, self).__iter__():
            yield self._postprocess_queryable_properties(obj)

    def _setup_queryable_properties(self):  # pragma: no cover
        """
        Set up potentially contained queryable properties to be handled
        correctly when executing the query.
        """
        pass

    def _postprocess_queryable_properties(self, obj):
        """
        Perform queryable property operations for the given loaded result
        object.

        :param obj: The object returned from the database.
        :return: The final object to return as part of the iterable.
        """
        return obj


class LegacyOrderingMixin(QueryablePropertiesIterableMixin):
    """
    A mixin for the legacy iterables that properly sets up queryable properties
    that are used for ordering.

    Old Django versions do not support ordering by annotations without
    explicitly selecting them, which is why non-selected properties used for
    ordering must be changed to selected properties.
    """

    @cached_property
    def _order_by_occurrences(self):
        """
        Cache and return a dictionary mapping queryable properties contained in
        the associated query to their indexes in the order by clause.

        Only contains property references for properties that are actually used
        for ordering.

        :return: A dictionary containing queryable property references as keys
                 and lists of indexes as values.
        :rtype: dict[queryable_properties.utils.internal.QueryablePropertyReference, list[int]]
        """
        query = self.queryset.query
        occurrences = {}
        for ref in query._queryable_property_annotations:
            annotation_name = six.text_type(ref.full_path)
            indexes = [index for index, field_name in enumerate(query.order_by)
                       if field_name in (annotation_name, '-{}'.format(annotation_name))]
            if indexes:
                occurrences[ref] = indexes
        return occurrences

    @cached_property
    def _order_by_select(self):
        """
        Cache and return a set containing the references for queryable
        properties that have to be forcibly selected as they are referenced in
        ordering while not being explicitly selected.

        :return: The set of references of properties that must be selected.
        :rtype: set[queryable_properties.utils.internal.QueryablePropertyReference]
        """
        query = self.queryset.query
        select = set()
        for ref, occurrences in six.iteritems(self._order_by_occurrences):
            annotation_name = six.text_type(ref.full_path)
            if annotation_name not in query.annotation_select and annotation_name in query.annotations:
                select.add(ref)
        return select

    def _setup_queryable_properties(self):
        super(LegacyOrderingMixin, self)._setup_queryable_properties()
        query = self.queryset.query
        select = dict(query.annotation_select)

        for property_ref in self._order_by_select:
            annotation_name = six.text_type(property_ref.full_path)
            select[annotation_name] = query.annotations[annotation_name]
        setattr(query, ANNOTATION_SELECT_CACHE_NAME, select)


class QueryablePropertiesModelIterableMixin(InjectableMixin, QueryablePropertiesIterableMixin):
    """
    A mixin for iterables that yield model instances.

    Removes the ``QUERYING_PROPERTIES_MARKER``from created model instances to
    ensure that the setters of queryable properties can be used properly.
    """

    def _setup_queryable_properties(self):
        super(QueryablePropertiesModelIterableMixin, self)._setup_queryable_properties()
        self.queryset.query._use_querying_properties_marker = True

    def _postprocess_queryable_properties(self, obj):
        obj = super(QueryablePropertiesModelIterableMixin, self)._postprocess_queryable_properties(obj)
        delattr(obj, QUERYING_PROPERTIES_MARKER)
        return obj


class LegacyModelIterable(QueryablePropertiesModelIterableMixin, LegacyIterable):
    """
    Legacy iterable class for querysets that yield model instances in Django
    versions that don't require additional ordering setup.
    """


class LegacyOrderingModelIterable(QueryablePropertiesModelIterableMixin, LegacyOrderingMixin, LegacyIterable):
    """
    Legacy iterable class for querysets that yield model instances in Django
    versions that require additional ordering setup.
    """

    def _postprocess_queryable_properties(self, obj):
        for ref in self._order_by_select:
            ref.descriptor.clear_cached_value(obj)
        return super(LegacyOrderingModelIterable, self)._postprocess_queryable_properties(obj)


class LegacyValuesIterable(LegacyOrderingMixin, LegacyIterable):
    """
    Legacy iterable class for querysets that yield value dictionaries.
    """

    def _postprocess_queryable_properties(self, obj):
        obj = super(LegacyValuesIterable, self)._postprocess_queryable_properties(obj)
        for ref in self._order_by_select:
            obj.pop(six.text_type(ref.full_path), None)
        return obj


class LegacyValuesListIterable(LegacyOrderingMixin, LegacyIterable):  # pragma: no cover
    """
    Legacy iterable class for querysets that yield value tuples.
    """

    def __init__(self, queryset, *args, **kwargs):
        super(LegacyValuesListIterable, self).__init__(queryset, *args, **kwargs)
        self.flat = queryset.flat
        self.queryset.flat = False

    @cached_property
    def _discarded_indexes(self):
        """
        Cache and return the field indexes of queryable properties that were
        only selected for ordering and must thus be discarded.

        All contained indexes will be negative, i.e. are to be interpreted as
        indexes from end of the returned rows.

        :return: A set containing the field indexes to discard.
        :rtype: set[int]
        """
        aggregate_names = list(self.queryset.query.aggregate_select)
        if self.queryset._fields:
            aggregate_names = [name for name in aggregate_names if name not in self.queryset._fields]
        aggregate_names.reverse()
        forced_names = set(six.text_type(ref.full_path) for ref in self._order_by_select)
        return {-i for i, name in enumerate(aggregate_names, start=1) if name in forced_names}

    def _postprocess_queryable_properties(self, obj):
        obj = super(LegacyValuesListIterable, self)._postprocess_queryable_properties(obj)
        obj = tuple(value for i, value in enumerate(obj, start=-len(obj)) if i not in self._discarded_indexes)
        if self.flat and len(self.queryset._fields) == 1:
            return obj[0]
        return obj


class QueryablePropertiesBaseQuerySetMixin(InjectableMixin):
    """
    Base mixin for queryable properties queryset mixins that takes care of
    injecting the appropriate query mixin into the associated query.
    """

    def init_injected_attrs(self):
        # To work correctly, a query using the QueryablePropertiesQueryMixin is
        # required. If the current query is not using the mixin already, it
        # will be dynamically injected into the query. That way, other Django
        # extensions using custom query objects are also supported.
        # Recent Django versions (>=3.1) have a property guarding the query
        # attribute.
        query_attr_name = '_query' if hasattr(self, '_query') else 'query'
        query = getattr(self, query_attr_name)
        chain_kwargs = {}
        if RawQuery and isinstance(query, RawQuery):
            chain_kwargs['using'] = self.db
        setattr(self, query_attr_name, inject_query_mixin(chain_query(query, **chain_kwargs)))


class QueryablePropertiesRawQuerySetMixin(QueryablePropertiesBaseQuerySetMixin):
    """
    A mixin for Django's :class:`django.db.models.RawQuerySet` objects that
    allows to populate queryable properties in raw queries.
    """

    def __iter__(self):
        original = super(QueryablePropertiesRawQuerySetMixin, self)
        # Only recent Django versions (>= 2.1) have the iterator method.
        iterator = original.__iter__ if hasattr(original, 'iterator') else self.iterator
        for obj in iterator():
            yield obj

    def iterator(self):
        iterable_class = RawModelIterable or LegacyIterable
        for obj in QueryablePropertiesModelIterableMixin.mix_with_class(iterable_class)(self):
            yield obj


class QueryablePropertiesQuerySetMixin(QueryablePropertiesBaseQuerySetMixin):
    """
    A mixin for Django's :class:`django.db.models.QuerySet` objects that allows
    to use queryable properties in filters, annotations and update queries.
    """

    @property
    def _iterable_class(self):
        # Override the regular _iterable_class attribute of recent Django
        # versions with a property that also stores the value in the instance
        # dict, but automatically mixes the
        # QueryablePropertiesModelIterableMixin into the base class on getter
        # access if the base class yields model instances. That way, the
        # queryable properties extensions stays compatible to custom iterable
        # classes while querysets can still be pickled due to the base class
        # being in the instance dict.
        cls = self.__dict__['_iterable_class']
        if issubclass(cls, ModelIterable):
            cls = QueryablePropertiesModelIterableMixin.mix_with_class(cls, 'QueryableProperties' + cls.__name__)
        return cls

    @_iterable_class.setter
    def _iterable_class(self, value):
        self.__dict__['_iterable_class'] = value

    def _clone(self, klass=None, *args, **kwargs):
        has_iterable_class = '_iterable_class' in self.__dict__
        if not has_iterable_class:  # pragma: no cover
            # In older Django versions, the class of the queryset may be
            # replaced with a dynamically created class based on the current
            # class and the value of klass while cloning (e.g when using
            # .values()). Therefore this needs to be re-injected to be on top
            # of the MRO again to enable queryable properties functionality.
            if klass:
                klass = QueryablePropertiesQuerySetMixin.mix_with_class(klass, 'QueryableProperties' + klass.__name__)
            args = (klass,) + args
        clone = super(QueryablePropertiesQuerySetMixin, self)._clone(*args, **kwargs)
        # Since the _iterable_class property may return a dynamically created
        # class, the value of a clone must be reset to the base class.
        if has_iterable_class:
            clone._iterable_class = self.__dict__['_iterable_class']
        return clone

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
                                             .format(prop))

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
                        .format(prop=prop, field=additional_name)
                    )
                kwargs[additional_name] = value

        return kwargs

    def select_properties(self, *names):
        """
        Add the annotations of the queryable properties with the specified
        names to this query. The annotation values will be cached in the
        properties of resulting model instances, regardless of the regular
        caching behavior of the queried properties.

        :param names: Names of queryable properties.
        :return: A copy of this queryset with the added annotations.
        :rtype: QuerySet
        """
        queryset = chain_queryset(self)
        for name in names:
            property_ref = QueryablePropertyReference(get_queryable_property(self.model, name), self.model, QueryPath())
            # A full GROUP BY is required if the query is not limited to
            # certain fields. Since only certain types of queries had the
            # _fields attribute in old Django versions, fall back to checking
            # for existing selection, on which the GROUP BY would be based.
            full_group_by = not getattr(self, '_fields', self.query.select)
            with queryset.query._add_queryable_property_annotation(property_ref, full_group_by, select=True):
                pass
        return queryset

    def iterator(self, *args, **kwargs):
        # Recent Django versions use their own iterable classes, where the
        # QueryablePropertiesModelIterableMixin will be already mixed in. In
        # older Django versions, the standalone legacy iterables are used
        # instead to perform the queryable properties processing. Exceptions
        # are legacy Date(Time)QuerySets, which don't support annotations
        # and override the ordering anyway as well as querysets that don't
        # yield model instances in Django 1.8, which doesn't require the
        # legacy ordering setup.
        if ('_iterable_class' not in self.__dict__ and
                not (isinstance(self, ValuesQuerySet) and not ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP) and
                not (DateQuerySet and isinstance(self, DateQuerySet)) and
                not (DateTimeQuerySet and isinstance(self, DateTimeQuerySet))):  # pragma: no cover
            iterable_class = LegacyOrderingModelIterable
            if not ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP:
                iterable_class = LegacyModelIterable
            elif isinstance(self, ValuesListQuerySet):
                iterable_class = LegacyValuesListIterable
            elif isinstance(self, ValuesQuerySet):
                iterable_class = LegacyValuesIterable
            return iter(iterable_class(self))
        return super(QueryablePropertiesQuerySetMixin, self).iterator(*args, **kwargs)

    def raw(self, *args, **kwargs):
        queryset = super(QueryablePropertiesQuerySetMixin, self).raw(*args, **kwargs)
        return QueryablePropertiesRawQuerySetMixin.inject_into_object(queryset)

    def update(self, **kwargs):
        # Resolve any queryable properties into their actual update kwargs
        # before calling the base update method.
        kwargs = self._resolve_update_kwargs(**kwargs)
        return super(QueryablePropertiesQuerySetMixin, self).update(**kwargs)

    @classmethod
    def apply_to(cls, queryset):
        """
        Copy the given queryset and apply this mixin (and thus queryable
        properties functionality) to it, returning a new queryset that allows
        to use queryable property interaction.

        :param QuerySet queryset: The queryset to apply this mixin to.
        :return: A copy of the given queryset with queryable properties
                 functionality.
        :rtype: QueryablePropertiesQuerySet
        """
        return cls.inject_into_object(chain_queryset(queryset))


class QueryablePropertiesQuerySet(QueryablePropertiesQuerySetMixin, QuerySet):
    """
    A special queryset class that allows to use queryable properties in its
    filter conditions, annotations and update queries.
    """

    @classmethod
    def get_for_model(cls, model):
        """
        Get a new queryset with queryable properties functionality for the
        given model. The queryset is built using the model's default manager.

        :param model: The model class for which the queryset should be built.
        :return: A new queryset with queryable properties functionality.
        :rtype: QueryablePropertiesQuerySet
        """
        return QueryablePropertiesQuerySetMixin.inject_into_object(model._default_manager.all())


class QueryablePropertiesManagerMixin(InjectableMixin):
    """
    A mixin for Django's :class:`django.db.models.Manager` objects that allows
    to use queryable properties methods and returns
    :class:`QueryablePropertiesQuerySet` instances.
    """

    def get_queryset(self):
        queryset = getattr(super(QueryablePropertiesManagerMixin, self), MANAGER_QUERYSET_METHOD_NAME)()
        return QueryablePropertiesQuerySetMixin.inject_into_object(queryset)

    get_query_set = get_queryset

    def select_properties(self, *names):
        """
        Return a new queryset and add the annotations of the queryable
        properties with the specified names to this query. The annotation
        values will be cached in the properties of resulting model instances,
        regardless of the regular caching behavior of the queried properties.

        :param names: Names of queryable properties.
        :return: A copy of this queryset with the added annotations.
        :rtype: QuerySet
        """
        return self.get_queryset().select_properties(*names)

    @classmethod
    def apply_to(cls, manager):
        """
        Copy the given manager and apply this mixin (and thus queryable
        properties functionality) to it, returning a new manager that allows
        to use queryable property interaction.

        :param Manager manager: The manager to apply this mixin to.
        :return: A copy of the given manager with queryable properties
                 functionality.
        :rtype: QueryablePropertiesManager
        """
        manager = copy(manager)
        manager.name = '<{}_with_queryable_properties>'.format(getattr(manager, 'name', None) or 'manager')
        return cls.inject_into_object(manager)


class QueryablePropertiesManager(QueryablePropertiesManagerMixin, Manager):
    """
    A special manager class that allows to use queryable properties methods
    and returns :class:`QueryablePropertiesQuerySet` instances.
    """

    @classmethod
    def get_for_model(cls, model, using=None, hints=None):
        """
        Get a new manager with queryable properties functionality for the
        given model.

        :param model: The model class for which the manager should be built.
        :param str | None using: An optional name of the database connection
                                 to use.
        :param dict | None hints: Optional hints for the db connection.
        :return: A new manager with queryable properties functionality.
        :rtype: QueryablePropertiesManager
        """
        manager = cls()
        manager.model = model
        manager.name = '<manager_with_queryable_properties>'
        manager._db = using
        manager._hints = hints or {}
        return manager
