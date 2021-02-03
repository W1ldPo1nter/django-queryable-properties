# encoding: utf-8

from __future__ import unicode_literals

import six
from django.db.models import Manager
from django.db.models.query import QuerySet

from .compat import (ANNOTATION_SELECT_CACHE_NAME, ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP, chain_query, chain_queryset,
                     LOOKUP_SEP, ModelIterable, ValuesQuerySet)
from .exceptions import QueryablePropertyDoesNotExist, QueryablePropertyError
from .query import QueryablePropertiesQueryMixin
from .utils import get_queryable_property
from .utils.internal import InjectableMixin, QueryablePropertyReference


class QueryablePropertiesIterable(InjectableMixin):
    """
    An iterable that yields the actual results of a queryset while correctly
    processing columns of queryable properties. It is closely related to
    Django's BaseIterable and will be used as a mixin for its subclasses in all
    (recent) Django versions that have it. In all other (older) versions, this
    class will be used as a standalone iterable instead.
    """

    def __init__(self, queryset, *args, **kwargs):
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
        :param args: Positional arguments to pass through to the base class
                     initialization when used as a mixin.
        :param kwargs: Keyword arguments to pass through to the base class
                       initialization when used as a mixin.
        :keyword collections.Iterable iterable: The optional iterable to use
                                                for standalone usage.
        """
        self.queryset = queryset
        # Only perform the super call if the class is used as a mixin
        if self.__class__.__bases__ != (InjectableMixin,):
            super(QueryablePropertiesIterable, self).__init__(queryset, *args, **kwargs)
        self.iterable = kwargs.get('iterable') or super(QueryablePropertiesIterable, self).__iter__()
        self.yields_model_instances = ((ModelIterable is not None and isinstance(self, ModelIterable)) or
                                       (ValuesQuerySet is not None and not isinstance(self.queryset, ValuesQuerySet)))

    def __iter__(self):
        """
        Yield the model objects for the queryset associated with this iterator
        with their correctly processed selected queryable properties.

        :return: A generator that yields the model objects.
        """
        original_query = self.queryset.query
        try:
            self.queryset.query = chain_query(original_query)
            final_aliases = self._setup_queryable_properties()

            for obj in self.iterable:
                if self.yields_model_instances:
                    # Retrieve the annotation values from each renamed
                    # attribute and use it to populate the cache for the
                    # corresponding queryable property on each object while
                    # removing the weird, renamed attributes.
                    for changed_name, property_ref in six.iteritems(final_aliases):
                        value = getattr(obj, changed_name)
                        delattr(obj, changed_name)
                        if property_ref:
                            property_ref.property._set_cached_value(obj, value)
                yield obj
        finally:
            self.queryset.query = original_query

    def _setup_queryable_properties(self):
        """
        Perform the required setup to correctly process queryable property
        values.

        Change the internal aliases of the annotations that belong to queryable
        properties in the query of the associated queryset to something unique
        and return a dictionary mapping the queryable properties to the changed
        aliases. This is necessary to allow Django to populate the annotation
        attributes on the resulting model instances, which would otherwise call
        the setter of the queryable properties. This way, Django can populate
        attributes with different names and avoid using the setter methods.

        Also make sure that ordering by queryable properties works in older
        Django versions.

        :return: A dictionary mapping the final aliases for queryable
                 properties to the corresponding references to be able to
                 retrieve the values from the DB and apply them to the correct
                 property. The property reference may be None, indicating that
                 the retrieved value should be discarded.
        :rtype: dict[str, QueryablePropertyReference | None]
        """
        query = self.queryset.query
        final_aliases = {}
        select = dict(query.annotation_select)

        for property_ref in query._queryable_property_annotations:
            annotation_name = property_ref.full_path

            # Older Django versions don't work with the annotation select dict
            # when it comes to ordering, so queryable property annotations used
            # for ordering need special treatment.
            order_by_occurrences = []
            if ANNOTATION_TO_AGGREGATE_ATTRIBUTES_MAP:  # pragma: no cover
                order_by_occurrences = [index for index, field_name in enumerate(query.order_by)
                                        if field_name == annotation_name or field_name[1:] == annotation_name]
                if order_by_occurrences and annotation_name not in select and annotation_name in query.annotations:
                    select[annotation_name] = query.annotations[annotation_name]
                    final_aliases[annotation_name] = None

            if not self.yields_model_instances or annotation_name not in select:
                # The queryable property annotation does not require selection
                # or no renaming needs to occur since the queryset doesn't
                # yield model instances.
                continue

            # Suffix the original annotation name with the lookup separator to
            # create a non-clashing name: both model field an queryable
            # property names are not allowed to contain the separator and a
            # relation path ending with the separator would be invalid as well.
            changed_name = ''.join((annotation_name, LOOKUP_SEP))
            final_aliases[changed_name] = final_aliases.pop(annotation_name, property_ref)
            select[changed_name] = select.pop(annotation_name)
            for index in order_by_occurrences:  # pragma: no cover
                # Apply the changed names to the ORDER BY clause.
                query.order_by[index] = query.order_by[index].replace(annotation_name, changed_name)

        # Patch the correct select property on the query with the new names,
        # since this property is used by the SQL compiler to build the actual
        # SQL query (which is where the changed names should be used).
        setattr(query, ANNOTATION_SELECT_CACHE_NAME, select)
        return final_aliases


class QueryablePropertiesQuerySetMixin(InjectableMixin):
    """
    A mixin for Django's :class:`django.db.models.QuerySet` objects that allows
    to use queryable properties in filters, annotations and update queries.
    """

    def init_injected_attrs(self):
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
        return QueryablePropertiesIterable.mix_with_class(cls, 'QueryableProperties' + cls.__name__)

    @_iterable_class.setter
    def _iterable_class(self, value):
        self.__dict__['_iterable_class'] = value

    def _clone(self, klass=None, *args, **kwargs):
        if klass:  # pragma: no cover
            # In older Django versions, the class of the queryset may be
            # replaced with a dynamically created class based on the current
            # class and the value of klass while cloning (e.g when using
            # .values()). Therefore this needs to be re-injected to be on top
            # of the MRO again to enable queryable properties functionality.
            klass = QueryablePropertiesQuerySetMixin.mix_with_class(klass, 'QueryableProperties' + klass.__name__)
            args = (klass,) + args
        clone = super(QueryablePropertiesQuerySetMixin, self)._clone(*args, **kwargs)
        # Since the _iterable_class property may return a dynamically created
        # class, the value of a clone must be reset to the base class.
        if '_iterable_class' in self.__dict__:
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
            property_ref = QueryablePropertyReference(get_queryable_property(self.model, name), self.model, ())
            # A full GROUP BY is required if the query is not limited to
            # certain fields. Since only certain types of queries had the
            # _fields attribute in old Django versions, fall back to checking
            # for existing selection, on which the GROUP BY would be based.
            full_group_by = not getattr(self, '_fields', self.query.select)
            with queryset.query._add_queryable_property_annotation(property_ref, full_group_by, select=True):
                pass
        return queryset

    def iterator(self, *args, **kwargs):
        # Recent Django versions use the associated iterable class for the
        # iterator() implementation, where the QueryablePropertiesModelIterable
        # will be already mixed in. In older Django versions, use a standalone
        # QueryablePropertiesModelIterable instead to perform the queryable
        # properties processing.
        iterable = super(QueryablePropertiesQuerySetMixin, self).iterator(*args, **kwargs)
        if '_iterable_class' not in self.__dict__:  # pragma: no cover
            return iter(QueryablePropertiesIterable(self, iterable=iterable))
        return iterable

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
