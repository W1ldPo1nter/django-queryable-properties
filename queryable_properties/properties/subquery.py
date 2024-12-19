# -*- coding: utf-8 -*-
import six

from ..apps import QueryablePropertiesConfig
from ..managers import QueryablePropertiesQuerySetMixin
from ..query import QUERYING_PROPERTIES_MARKER
from ..utils import QueryPath
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

    def __init__(self, queryset, field_names=None, property_names=(), **kwargs):
        """
        Initialize a new property that allows to fetch an entire model object
        from the first row of a given subquery.

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
        super(SubqueryObjectProperty, self).__init__(queryset, 'pk', **kwargs)
        self._descriptor = None
        self._field_names = field_names
        self._property_names = property_names
        self._sub_property_refs = {}
        self._field_aliases = {}

    def _build_sub_properties(self):
        """
        Construct the sub-properties this property builds on, attach them to
        the model class and store references to them in attributes.
        """
        def add_sub_property(name, queryset):
            prop = SubqueryFieldProperty(queryset, name, cached=self.cached)
            prop.contribute_to_class(self.model, '-'.join((self.name, name)))
            self._sub_property_refs[name] = prop._get_ref()

        for field in self.queryset.model._meta.concrete_fields:
            if field.primary_key or (self._field_names is not None and field.name not in self._field_names):
                continue
            add_sub_property(field.attname, self.queryset)
            if field.name != field.attname:
                self._field_aliases[field.name] = field.attname
        for property_name in self._property_names:
            add_sub_property(property_name,
                             QueryablePropertiesQuerySetMixin.apply_to(self.queryset).select_properties(property_name))

    def _determine_ref_by_path(self, path, model=None, relation_path=QueryPath()):
        """
        Determine the correct property reference to use for the given path.

        The result may be a reference to one of the sub-properties or a
        reference to this property as a regular
        :class:`QueryablePropertyReference`.

        :param QueryPath path: The query path to determine the reference by.
        :param type | None model: The model class the property is being
                                  referenced on. If not provided, this defaults
                                  to the model the property is defined on.
        :param QueryPath relation_path: The path representing the relation the
                                        property is being referenced across.
        :return: A 2-tuple containing the final reference as well as the
                 remaining path.
        :rtype: (QueryablePropertyReference, QueryPath)
        """
        if path:
            first = self._field_aliases.get(path[0], path[0])
            if first in self._sub_property_refs:
                # Reference to one of the fields represented by the sub-properties.
                ref = self._sub_property_refs[first]._replace(model=model or self.model, relation_path=relation_path)
                return ref, path[1:]
            if first in ('pk', self.queryset.model._meta.pk.name, self.queryset.model._meta.pk.attname):
                # Reference to the primary key field represented by this property.
                path = path[1:]
        return super(SubqueryObjectProperty, self)._get_ref(model, relation_path), path

    def _get_ref(self, model=None, relation_path=QueryPath()):
        return SubqueryObjectPropertyReference(self, model or self.model, relation_path)

    def contribute_to_class(self, cls, name):
        super(SubqueryObjectProperty, self).contribute_to_class(cls, name)
        self._descriptor = getattr(cls, name)
        self._descriptor._ignore_cached_value = True
        # Build SubqueryFieldProperty objects for each field after Django is
        # done initializing.
        QueryablePropertiesConfig.add_ready_callback(self._build_sub_properties)

    def get_value(self, obj):
        if not self._descriptor.has_cached_value(obj):
            # No value is cached at all: perform a single query to fetch the
            # values for all fields and populate the cache for this property
            # and all sub-properties.
            names = [ref.property.name for ref in six.itervalues(self._sub_property_refs)]
            names.append(self.name)
            values = self.get_queryset_for_object(obj).select_properties(*names).values(*names).get()
            self._descriptor.set_cached_value(obj, values[self.name])
            for ref in six.itervalues(self._sub_property_refs):
                ref.descriptor.set_cached_value(obj, values[ref.property.name])

        value = self._descriptor.get_cached_value(obj)
        if not isinstance(value, self.queryset.model):
            # The cached value is a raw primary key. Use this value and the
            # present cache values of all sub-properties to construct the final
            # model instance.
            names, values = [], []
            for field in self.queryset.model._meta.concrete_fields:
                if field.primary_key:
                    values.append(value)
                elif (field.attname in self._sub_property_refs and
                        self._sub_property_refs[field.attname].descriptor.has_cached_value(obj)):
                    values.append(self._sub_property_refs[field.attname].descriptor.get_cached_value(obj))
                else:
                    continue
                names.append(field.attname)
            value = self.queryset.model.from_db(self.queryset.db, names, values)

            # Populate any queryable properties whose values were queried for
            # the subquery object.
            setattr(value, QUERYING_PROPERTIES_MARKER, True)
            for property_name in self._property_names:
                descriptor = self._sub_property_refs[property_name].descriptor
                if descriptor.has_cached_value(obj):
                    setattr(value, property_name, descriptor.get_cached_value(obj))
            delattr(value, QUERYING_PROPERTIES_MARKER)

            self._descriptor.set_cached_value(obj, value)
        return value

    def get_filter(self, cls, lookup, value):
        if isinstance(value, self.queryset.model):
            value = value.pk
        ref, lookup = self._determine_ref_by_path(QueryPath(lookup))
        return (ref.full_path + lookup).build_filter(value)


class SubqueryObjectPropertyReference(QueryablePropertyReference):
    """
    A specialized property reference that allows the parts of a
    :class:`SubqueryObjectProperty` to be annotated properly.
    """
    __slots__ = ()

    def annotate_query(self, query, full_group_by, select=False, remaining_path=QueryPath()):
        if select and not remaining_path:
            # A selection of the main property via .select_properties()
            # should lead to the selection of all sub-properties to be able to
            # populate the subquery object with all values.
            for ref in six.itervalues(self.property._sub_property_refs):
                ref = ref._replace(model=self.model, relation_path=self.relation_path)
                ref.annotate_query(query, full_group_by, select)
        final_ref, remaining_path = self.property._determine_ref_by_path(remaining_path, self.model, self.relation_path)
        return final_ref.annotate_query(query, full_group_by, select, remaining_path)
