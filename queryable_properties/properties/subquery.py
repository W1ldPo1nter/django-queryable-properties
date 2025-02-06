# -*- coding: utf-8 -*-
import six
from django.db.models import Q

from ..managers import QueryablePropertiesQuerySetMixin
from ..utils import get_queryable_property
from ..utils.internal import QueryPath, get_output_field, get_queryable_property_descriptor
from .base import QueryableProperty, QueryablePropertyReference
from .mixins import SubqueryMixin


class SubqueryFieldProperty(SubqueryMixin, QueryableProperty):
    """
    A property that returns a field value contained in a subquery, extracting
    it from the first row of the subquery's result set.
    """

    def __init__(self, queryset, field_name, output_field=None, **kwargs):
        """
        Initialize a new property that returns a field value from a subqery.

        :param queryset: The internal queryset to use as the subquery or a
                         callable without arguments that generates the internal
                         queryset.
        :type queryset: django.db.models.QuerySet | function
        :param str field_name: The name of the subquery field whose value
                               should be returned. May refer to an annotated
                               field or queryable property inside the subquery.
        :param output_field: The output field to use for the subquery
                             expression. Only required in cases where Django
                             cannot determine the field type on its own.
        :type output_field: django.db.models.Field | None
        """
        self.field_name = field_name
        self.output_field = output_field
        super(SubqueryFieldProperty, self).__init__(queryset, **kwargs)

    def get_annotation(self, cls):
        from django.db.models import Subquery

        return Subquery(self.queryset.values(self.field_name)[:1], output_field=self.output_field)


class SubqueryExistenceCheckProperty(SubqueryMixin, QueryableProperty):
    """
    A property that checks whether certain objects exist in the database using
    a custom subquery.
    """

    def __init__(self, queryset, negated=False, **kwargs):
        """
        Initialize a new property that checks for the existence of database
        records using a custom subquery.

        :param queryset: The internal queryset to use as the subquery or a
                         callable without arguments that generates the internal
                         queryset.
        :type queryset: django.db.models.QuerySet | function
        :param bool negated: Whether to negate the ``EXISTS`` subquery (i.e.
                             the property will return ``True`` if no objects
                             exist when using ``negated=True``).
        """
        self.negated = negated
        super(SubqueryExistenceCheckProperty, self).__init__(queryset, **kwargs)

    def get_annotation(self, cls):
        from django.db.models import Exists

        subquery = Exists(self.queryset)
        if self.negated:
            subquery = ~subquery
        return subquery


class SubqueryObjectProperty(SubqueryFieldProperty):
    """
    A property that allows to fetch an entire model object from the first row
    of a given subquery.

    Each field value of the subquery object is queried using a
    :class:`SubqueryFieldProperty`. A model instance is reconstructed from the
    individual field values.
    """

    def __init__(self, model, queryset, field_names=None, property_names=(), **kwargs):
        """
        Initialize a new property that allows to fetch an entire model object
        from the first row of a given subquery.

        :param model: The model class whose instances are being queried via the
                      subquery. Can be either a concrete model class or a lazy
                      reference to a model class (see foreign keys).
        :type model: type | str
        :param queryset: The internal queryset to use as the subquery or a
                         callable without arguments that generates the internal
                         queryset.
        :type queryset: django.db.models.QuerySet | function
        :param field_names: The names of the fields that should be queried for
                            the subquery object. Fields not present in this
                            sequence will be deferred. If not provided, all
                            concrete fields of the model will be queried.
        :type field_names: collections.Sequence[str] | None
        :param property_names: Optional names of queryable properties on the
                               subquery model whose values should be retrieved
                               along with the other fields. If not provided, no
                               queryable property values will be selected.
        :type property_names: collections.Sequence[str]
        """
        kwargs.pop('output_field', None)
        super(SubqueryObjectProperty, self).__init__(queryset, None, **kwargs)
        self._descriptor = None
        self._subquery_model = model
        self._field_names = field_names
        self._property_names = property_names
        self._managed_refs = {}
        self._field_aliases = {}
        self._pk_field_names = None

    def _finalize_setup(self, model, subquery_model):
        """
        Finalize the setup of this property by constructing the sub-properties,
        attaching them to the model class and populating attributes.
        """
        pk_fields = getattr(subquery_model._meta, 'pk_fields', [subquery_model._meta.pk])
        sub_field_names = set(self._field_names) if self._field_names is not None else None

        self._subquery_model = subquery_model
        self._pk_field_names = [pk_field.attname for pk_field in pk_fields]
        self.field_name = self._pk_field_names[0]
        self._managed_refs[self.field_name] = QueryablePropertyReference(self, self.model, QueryPath())
        if pk_fields[0].name != self.field_name:
            self._field_aliases[pk_fields[0].name] = self.field_name
        if len(pk_fields) == 1:
            self._field_aliases['pk'] = self.field_name
        elif sub_field_names is not None:
            sub_field_names.update(pk_field.name for pk_field in pk_fields[1:])

        def add_sub_property(name, queryset, output_field=None):
            prop = SubqueryFieldProperty(queryset, name, output_field=output_field, cached=self.cached)
            prop.contribute_to_class(model, '-'.join((self.name, name)))
            self._managed_refs[name] = prop._resolve()[0]

        for field in subquery_model._meta.concrete_fields:
            if field is pk_fields[0] or (sub_field_names is not None and field.name not in sub_field_names):
                continue
            add_sub_property(field.attname, self._queryset)
            if field.name != field.attname:
                self._field_aliases[field.name] = field.attname
        for property_name in self._property_names:
            remote_ref = get_queryable_property(subquery_model, property_name)._resolve(subquery_model)[0]
            add_sub_property(
                property_name,
                lambda: QueryablePropertiesQuerySetMixin.apply_to(self.queryset).select_properties(property_name),
                get_output_field(remote_ref.get_annotation()),
            )

    def _resolve(self, model=None, relation_path=QueryPath(), remaining_path=QueryPath()):
        if remaining_path:
            first = self._field_aliases.get(remaining_path[0], remaining_path[0])
            if first in self._managed_refs:
                # Reference to one of the fields represented by the managed
                # properties.
                ref = self._managed_refs[first]._replace(model=model or self.model, relation_path=relation_path)
                return ref, remaining_path[1:]
        return SubqueryObjectPropertyReference(self, model or self.model, relation_path), remaining_path

    def contribute_to_class(self, cls, name):
        from django.db.models.fields.related import lazy_related_operation

        super(SubqueryObjectProperty, self).contribute_to_class(cls, name)
        self._descriptor = getattr(cls, name)
        self._descriptor._ignore_cached_value = True
        # Finalize the setup of this property after the subquery model was
        # constructed.
        lazy_related_operation(self._finalize_setup, self.model, self._subquery_model)

    def get_value(self, obj):
        values = {}
        if self._descriptor.has_cached_value(obj):
            cached_value = self._descriptor.get_cached_value(obj)
            if cached_value is None or isinstance(cached_value, self._subquery_model):
                # The cached value is already the final model object or None,
                # so it can be returned as-is.
                return cached_value

            # The cached value is a raw primary key. Use this value and the
            # present cache values of all managed properties to construct the
            # final model instance.
            for attname, ref in six.iteritems(self._managed_refs):
                if ref.descriptor.has_cached_value(obj):
                    values[ref.property.name] = ref.descriptor.get_cached_value(obj)
                elif attname in self._pk_field_names:
                    # For composite PKs, all fields contributing to the PK must have
                    # a value, otherwise the cached values can't be used.
                    values.clear()
                    break

        if not values:
            # No/insufficient cached values: perform a single query to fetch
            # the values for all fields and populate the cache for all managed
            # properties if configured as cached.
            names = [ref.property.name for ref in six.itervalues(self._managed_refs)]
            values = self.get_queryset_for_object(obj).select_properties(*names).values(*names).get()
            if self.cached:
                for ref in six.itervalues(self._managed_refs):
                    ref.descriptor.set_cached_value(obj, values[ref.property.name])
            if values[self.name] is None:
                # The subquery didn't return a row, so no instance can be
                # constructed.
                return None

        field_names, field_values = [], []
        for field in self._subquery_model._meta.concrete_fields:
            if field.attname in self._managed_refs and self._managed_refs[field.attname].property.name in values:
                field_names.append(field.attname)
                field_values.append(values[self._managed_refs[field.attname].property.name])
        subquery_obj = self._subquery_model.from_db(self.queryset.db, field_names, field_values)

        # Populate any queryable properties whose values were queried for the
        # subquery object.
        for property_name in self._property_names:
            sub_name = self._managed_refs[property_name].property.name
            if sub_name in values:
                get_queryable_property_descriptor(self._subquery_model, property_name).set_cached_value(
                    subquery_obj, values[sub_name])

        if self.cached or self._descriptor.has_cached_value(obj):
            self._descriptor.set_cached_value(obj, subquery_obj)
        return subquery_obj

    def get_filter(self, cls, lookup, value):
        if isinstance(value, self._subquery_model):
            value = value.pk
        if len(self._pk_field_names) > 1 and isinstance(value, tuple):
            # Build individual filter clauses for each field of a composite PK.
            base_path = QueryPath(self.name)
            conditions = {(base_path + lookup).as_str(): value[0]}
            for attname, pk_part in zip(self._pk_field_names[1:], value[1:]):
                conditions[(base_path + attname + lookup).as_str()] = pk_part
            return Q(**conditions)
        return super(SubqueryObjectProperty, self).get_filter(cls, lookup, value)


class SubqueryObjectPropertyReference(QueryablePropertyReference):
    """
    A specialized property reference that allows the parts of a
    :class:`SubqueryObjectProperty` to be annotated properly.
    """
    __slots__ = ()

    def annotate_query(self, query, full_group_by, select=False, remaining_path=QueryPath()):
        if select:
            # A selection of the main property via .select_properties()
            # should lead to the selection of all sub-properties to be able to
            # populate the subquery object with all values.
            for ref in six.itervalues(self.property._managed_refs):
                if ref.property is not self.property:
                    ref = ref._replace(model=self.model, relation_path=self.relation_path)
                    ref.annotate_query(query, full_group_by, select)
        return super(SubqueryObjectPropertyReference, self).annotate_query(query, full_group_by, select, remaining_path)
