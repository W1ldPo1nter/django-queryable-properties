# encoding: utf-8

import operator

import six
from django.db.models import Field

from ..utils.internal import MISSING_OBJECT, ModelAttributeGetter
from .base import QueryableProperty
from .mixins import AnnotationMixin, BooleanMixin


class ValueCheckProperty(BooleanMixin, AnnotationMixin, QueryableProperty):
    """
    A property that checks if an attribute of a model instance or a related
    object contains a certain value or one of multiple specified values and
    returns a corresponding boolean value.

    Supports queryset filtering and ``CASE``/``WHEN``-based annotating.
    """

    def __init__(self, attribute_path, *values, **kwargs):
        """
        Initialize a new property that checks for certain field values.

        :param str attribute_path: The name of the attribute to compare
                                   against. May also be a more complex path to
                                   a related attribute using dot-notation (like
                                   with :func:`operator.attrgetter`). If an
                                   intermediate value on the path is None, it
                                   will be treated as "no match" instead of
                                   raising an exception. The behavior is the
                                   same if an intermediate value raises an
                                   ObjectDoesNotExist error.
        :param values: The value(s) to check for.
        """
        self.attribute_getter = ModelAttributeGetter(attribute_path)
        self.values = values
        super(ValueCheckProperty, self).__init__(**kwargs)

    def get_value(self, obj):
        return self.attribute_getter.get_value(obj) in self.values

    def _get_condition(self, cls):
        return self.attribute_getter.build_filter('in', self.values)


class RangeCheckProperty(BooleanMixin, AnnotationMixin, QueryableProperty):
    """
    A property that checks if a static or dynamic value is contained in a range
    expressed by two field values and returns a corresponding boolean value.

    Supports queryset filtering and ``CASE``/``WHEN``-based annotating.
    """

    def __init__(self, min_attribute_path, max_attribute_path, value, include_boundaries=True, in_range=True,
                 include_missing=False, **kwargs):
        """
        Initialize a new property that checks if a value is contained in a
        range expressed by two field values.

        :param str min_attribute_path: The name of the attribute to get the
                                       lower boundary from. May also be a more
                                       complex path to a related attribute
                                       using dot-notation (like with
                                       :func:`operator.attrgetter`). If an
                                       intermediate value on the path is None,
                                       it will be treated as a missing value
                                       instead of raising an exception. The
                                       behavior is the same if an intermediate
                                       value raises an ``ObjectDoesNotExist``
                                       error.
        :param str max_attribute_path: The name of the attribute to get the
                                       upper boundary from. The same behavior
                                       as for the lower boundary applies.
        :param value: The value which is tested against the boundary. May be a
                      callable which can be called without any arguments, whose
                      return value will then be used as the test value.
        :param bool include_boundaries: Whether or not the value is considered
                                        a part of the range if it is exactly
                                        equal to one of the boundaries.
        :param bool in_range: Configures whether the property should return
                              ``True`` if the value is in range
                              (``in_range=True``) or if it is out of the range
                              (``in_range=False``). This also affects the
                              impact of the ``include_boundaries`` and
                              ``include_missing`` parameters.
        :param bool include_missing: Whether or not a missing value is
                                     considered a part of the range (see the
                                     description of ``min_attribute_path``).
                                     Useful e.g. for nullable fields.
        """
        self.min_attribute_getter = ModelAttributeGetter(min_attribute_path)
        self.max_attribute_getter = ModelAttributeGetter(max_attribute_path)
        self.value = value
        self.include_boundaries = include_boundaries
        self.in_range = in_range
        self.include_missing = include_missing
        super(RangeCheckProperty, self).__init__(**kwargs)

    @property
    def final_value(self):
        value = self.value
        if callable(value):
            value = value()
        return value

    def get_value(self, obj):
        value = self.final_value
        min_value = self.min_attribute_getter.get_value(obj)
        max_value = self.max_attribute_getter.get_value(obj)
        lower_operator = operator.le if self.include_boundaries else operator.lt
        greater_operator = operator.ge if self.include_boundaries else operator.gt
        contained = self.include_missing if min_value in (None, MISSING_OBJECT) else greater_operator(value, min_value)
        contained &= self.include_missing if max_value in (None, MISSING_OBJECT) else lower_operator(value, max_value)
        return not (contained ^ self.in_range)

    def _get_condition(self, cls):
        value = self.final_value
        lower_condition = self.min_attribute_getter.build_filter('lte' if self.include_boundaries else 'lt', value)
        upper_condition = self.max_attribute_getter.build_filter('gte' if self.include_boundaries else 'gt', value)
        if self.include_missing:
            lower_condition |= self.min_attribute_getter.build_filter('isnull', True)
            upper_condition |= self.max_attribute_getter.build_filter('isnull', True)
        if not self.in_range:
            return ~lower_condition | ~upper_condition
        return lower_condition & upper_condition


class MappingProperty(AnnotationMixin, QueryableProperty):
    """
    A property that translates values of an attribute into other values using
    defined mappings.
    """

    # Copy over Django's implementation to forcibly evaluate a lazy value.
    _force_value = six.get_unbound_function(Field.get_prep_value)

    def __init__(self, attribute_path, output_field, mappings, default=None, **kwargs):
        """
        Initialize a property that maps values from an attribute to other
        values.

        :param str attribute_path: The name of the attribute to compare
                                   against. May also be a more complex path to
                                   a related attribute using dot-notation (like
                                   with :func:`operator.attrgetter`). If an
                                   intermediate value on the path is None, it
                                   will be treated as "no match" instead of
                                   raising an exception. The behavior is the
                                   same if an intermediate value raises an
                                   ``ObjectDoesNotExist`` error.
        :param django.db.models.Field output_field: The field to represent the
                                                    mapped values in querysets.
        :param mappings: An iterable containing 2-tuples that represent the
                         mappings to use (the first value of each tuple is
                         mapped to the second value).
        :type mappings: collections.Iterable[(object, object)]
        :param default: A default value to return/use in querysets when in case
                        none of the mappings match an encountered value.
                        Defaults to None.
        """
        super(MappingProperty, self).__init__(**kwargs)
        self.attribute_getter = ModelAttributeGetter(attribute_path)
        self.output_field = output_field
        self.mappings = mappings
        self.default = default

    def get_value(self, obj):
        attibute_value = self.attribute_getter.get_value(obj)
        for from_value, to_value in self.mappings:
            if attibute_value == from_value:
                return self._force_value(to_value)
        return self._force_value(self.default)

    def get_annotation(self, cls):
        from django.db.models import Case, Value, When

        cases = (When(self.attribute_getter.build_filter('exact', from_value), then=Value(self._force_value(to_value)))
                 for from_value, to_value in self.mappings)
        return Case(*cases, default=Value(self._force_value(self.default)), output_field=self.output_field)
