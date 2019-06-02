# encoding: utf-8

from __future__ import unicode_literals

import uuid

from django.db.models import Manager
from django.db.models.query import QuerySet
from django.utils import six

from .compat import (ANNOTATION_SELECT_CACHE_NAME, ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP, chain_query, chain_queryset,
                     LOOKUP_SEP, ModelIterable, ValuesQuerySet)
from .exceptions import QueryablePropertyDoesNotExist, QueryablePropertyError
from .query import QueryablePropertiesQueryMixin
from .utils import get_queryable_property, InjectableMixin


class QueryablePropertiesModelIterable(InjectableMixin):
    """
    An iterable that yields model instances for each returned database row
    while correctly processing columns of queryable properties. It is closely
    related to Django's ModelIterable and will be used as a mixin for this
    class in all (recent) Django versions that have it. In all other versions,
    this class will be used as a standalone iterable.
    """

    def __init__(self, queryset, iterable=None, **kwargs):
        """
        Initialize a new iterable for the given queryset. If an iterable is
        given it will be used to retrieve the model instances before applying
        queryable properties logic (standalone usage for older Django
        versions). Otherwise, the __iter__ implementation of the base class
        is used to get the model instances (usage as mixin).

        :param QuerySet queryset: The queryset to perform the database query
                                  for.
        :param collections.Iterable iterable: The optional iterable to use for
                                              standalone usage.
        :param kwargs: Keyword arguments to pass through to the base class
                       initialization when used as a mixin.
        """
        self.queryset = queryset
        # Only perform the super call if the class is used as a mixin
        if self.__class__.__bases__ != (InjectableMixin,):
            super(QueryablePropertiesModelIterable, self).__init__(queryset, **kwargs)
        self.iterable = iterable or super(QueryablePropertiesModelIterable, self).__iter__()

    def __iter__(self):
        """
        Yield the model objects for the queryset associated with this iterator
        with their correctly processed selected queryable properties.

        :return: A generator that yields the model objects.
        """
        # Annotation caching magic happens here: If this queryset is about to
        # actually perform an SQL query, the queryable property annotations
        # need to be renamed so Django doesn't call their setter. The renaming
        # and the actual query execution will be performed on a clone of the
        # current query object. That way, the query object can then be changed
        # back to the original one where nothing was renamed and can be used
        # for the constructions of further querysets based on this one.
        original_query = self.queryset.query

        try:
            self.queryset.query = chain_query(original_query)
            changed_aliases = self._change_queryable_property_aliases()

            for obj in self.iterable:
                # Retrieve the annotation values from each renamed attribute
                # and use it to populate the cache for the corresponding
                # queryable property on each object while removing the weird,
                # renamed attributes.
                for prop, changed_name in six.iteritems(changed_aliases):
                    value = getattr(obj, changed_name)
                    delattr(obj, changed_name)
                    # The following check is only required for older Django
                    # versions, where all annotations were necessarily
                    # selected. Therefore values that have been selected only
                    # due to this will simply be discarded.
                    if self.queryset.query._queryable_property_annotations[prop]:
                        prop._set_cached_value(obj, value)
                yield obj
        finally:
            self.queryset.query = original_query

    def _change_queryable_property_aliases(self):
        """
        Change the internal aliases of the annotations that belong to queryable
        properties in the query of the associated queryset to something unique
        and return a dictionary mapping the queryable properties to the changed
        aliases. This is necessary to allow Django to populate the annotation
        attributes on the resulting model instances, which would otherwise call
        the setter of the queryable properties. This way, Django can populate
        attributes with different names and avoid using the setter methods.

        :return: A dictionary mapping the queryable properties that selected
                 annotations are based on to the changed aliases.
        :rtype: dict[queryable_properties.properties.QueryableProperty, str]
        """
        query = self.queryset.query
        changed_aliases = {}
        select = dict(query.annotation_select)

        for prop, requires_selection in query._queryable_property_annotations.items():
            if prop.name not in select:
                continue  # Annotations may have been removed somehow

            # Older Django versions didn't make a clear distinction between
            # selected an non-selected annotations, therefore non-selected
            # annotations can only be removed from the annotation select dict
            # in newer versions (to not unnecessarily query fields).
            if not requires_selection and not ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP:
                select.pop(prop.name, None)
                continue

            changed_name = prop.name
            # Suffix the original annotation names with random UUIDs until an
            # available name can be found. Since the suffix is delimited by
            # the lookup separator, these names are guaranteed to not clash
            # with names of model fields, which don't allow the separator in
            # their names.
            while changed_name in query.annotations:
                changed_name = LOOKUP_SEP.join((prop.name, uuid.uuid4().hex))
            changed_aliases[prop] = changed_name
            select[changed_name] = select.pop(prop.name)

            # Older Django versions only work with the annotation select dict
            # when it comes to ordering, so queryable property annotations used
            # for ordering must be renamed in the query's ordering as well.
            if ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP:  # pragma: no cover
                for i, field_name in enumerate(query.order_by):
                    if field_name == prop.name or field_name[1:] == prop.name:
                        query.order_by[i] = field_name.replace(prop.name, changed_name)

        # Patch the correct select property on the query with the new names,
        # since this property is used by the SQL compiler to build the actual
        # SQL query (which is where the the changed names should be used).
        setattr(query, ANNOTATION_SELECT_CACHE_NAME, select)
        return changed_aliases


class QueryablePropertiesQuerySetMixin(InjectableMixin):
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
            self.query = chain_query(self.query)
            class_name = 'QueryableProperties' + self.query.__class__.__name__
            QueryablePropertiesQueryMixin.inject_into_object(self.query, class_name)

    @property
    def _iterable_class(self):
        # Override the regular _iterable_class attribute of recent Django
        # versions with a property that also stores the value in the instance
        # dict, but automatically mixes the QueryablePropertiesModelIterable
        # into the base class on getter access if the base class yields model
        # instances. That way, the queryable properties extensions stays
        # compatible to custom iterable classes while querysets can still be
        # pickled due to the base class being in the instance dict.
        cls = self.__dict__['_iterable_class']
        if not issubclass(cls, ModelIterable):
            return cls
        return QueryablePropertiesModelIterable.mix_with_class(cls, 'QueryableProperties' + cls.__name__)

    @_iterable_class.setter
    def _iterable_class(self, value):
        self.__dict__['_iterable_class'] = value

    def _clone(self, *args, **kwargs):
        clone = super(QueryablePropertiesQuerySetMixin, self)._clone(*args, **kwargs)
        # Since the _iterable_class property may return a dynamically created
        # class, the value of a clone must be reset to the base class.
        if '_iterable_class' in self.__dict__:
            clone._iterable_class = self.__dict__['_iterable_class']
        # In older Django versions, the class of the property may be completely
        # replaced while cloning (e.g when using .values()). Therefore this
        # mixin might need to be re-injected to enable queryable properties
        # functionality.
        if not isinstance(clone, QueryablePropertiesQuerySetMixin):  # pragma: no cover
            class_name = 'QueryableProperties' + clone.__class__.__name__
            QueryablePropertiesQuerySetMixin.inject_into_object(clone, class_name)
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
            prop = get_queryable_property(self.model, name)
            # A full GROUP BY is required if the query is not limited to certain
            # fields. Since only certain types of queries had the _fields attribute
            # in old Django versions, fall back to checking for existing grouping.
            full_group_by = not getattr(self, '_fields', self.query.group_by)
            queryset.query.add_queryable_property_annotation(prop, select=True, full_group_by=full_group_by)
        if ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP and isinstance(self, ValuesQuerySet):  # pragma: no cover
            # In older Django versions, the annotation mask was changed by the
            # queryset itself when applying annotations to a ValuesQuerySet.
            # Therefore the same must be done here in this case.
            queryset.query.set_aggregate_mask((queryset.query.aggregate_select_mask or set()) | set(names))
        return queryset

    def iterator(self, *args, **kwargs):
        # Recent Django versions use the associated iterable class for the
        # iterator() implementation, where the QueryablePropertiesModelIterable
        # will be already mixed in. In older Django versions, use a standalone
        # QueryablePropertiesModelIterable instead to perform the queryable
        # properties processing (as long as this queryset returns model
        # instances).
        iterable = super(QueryablePropertiesQuerySetMixin, self).iterator(*args, **kwargs)
        if ValuesQuerySet and not isinstance(self, ValuesQuerySet):  # pragma: no cover
            return iter(QueryablePropertiesModelIterable(self, iterable))
        return iterable

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

        get_query_set = get_queryset

        def select_properties(self, *names):
            return self.get_queryset().select_properties(*names)
