# encoding: utf-8

import operator

from django.db.models import BooleanField, Q

from ..compat import LOOKUP_SEP
from ..utils import ModelAttributeGetter
from .base import QueryableProperty
from .mixins import AnnotationMixin, boolean_filter, LookupFilterMixin


class BooleanProperty(LookupFilterMixin, AnnotationMixin, QueryableProperty):
    """
    Internal base class for common properties that return boolean values.
    """

    filter_requires_annotation = False

    def _get_condition(self):  # pragma: no cover
        """
        Build the query filter condition for this boolean property, which is
        used for both the filter and the annotation implementation.

        :return: The filter condition for this property.
        :rtype: django.db.models.Q
        """
        raise NotImplementedError()

    @boolean_filter
    def get_exact_filter(self, cls):
        return self._get_condition()

    def get_annotation(self, cls):
        from django.db.models import Case, When

        return Case(
            When(self._get_condition(), then=True),
            default=False,
            output_field=BooleanField()
        )


class ValueCheckProperty(BooleanProperty):
    """
    A property that checks if an attribute of a model instance or a related
    object contains a certain value or one of multiple specified values and
    returns a corresponding boolean value.

    Supports queryset filtering and CASE/WHEN-based annotating.
    """

    def __init__(self, attribute_path, *values):
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
        super(ValueCheckProperty, self).__init__()

    def get_value(self, obj):
        return self.attribute_getter.get_value(obj) in self.values

    def _get_condition(self):
        return self.attribute_getter.build_filter('in', self.values)


class RangeCheckProperty(BooleanProperty):
    """
    A property that checks if a static or dynamic value is contained in a range
    expressed by two field values and returns a corresponding boolean value.

    Supports queryset filtering and CASE/WHEN-based annotating.
    """

    def __init__(self, min_field_name, max_field_name, value, include_boundaries=True, in_range=True):
        """
        Initialize a new property that checks if a value is contained in a
        range expressed by two field values.

        :param str min_field_name: The name of the field to get the lower
                                   boundary from.
        :param str max_field_name: The name of the field to get the upper
                                   boundary from.
        :param value: The value which is tested against the boundary. May be a
                      callable which can be called without any arguments, whose
                      return value will then be used as the test value.
        :param bool include_boundaries: Whether or not the value is considered
                                        a part of the range if it is exactly
                                        equal to one of the boundaries.
        :param bool in_range: Configures whether the property should return
                              `True` if the value is in range (`in_range=True`)
                              or if it is out of the range (`in_range=False`).
        """
        self.min_field_name = min_field_name
        self.max_field_name = max_field_name
        self.value = value
        self.include_boundaries = include_boundaries
        self.in_range = in_range
        super(RangeCheckProperty, self).__init__()

    @property
    def final_value(self):
        value = self.value
        if callable(value):
            value = value()
        return value

    def get_value(self, obj):
        value = self.final_value
        lower_operator = operator.le if self.include_boundaries else operator.lt
        greater_operator = operator.ge if self.include_boundaries else operator.gt
        contained = (greater_operator(value, getattr(obj, self.min_field_name)) and
                     lower_operator(value, getattr(obj, self.max_field_name)))
        return not (contained ^ self.in_range)

    def _get_condition(self):
        value = self.final_value
        condition = Q(**{
            LOOKUP_SEP.join((self.max_field_name, 'gte' if self.include_boundaries else 'gt')): value,
            LOOKUP_SEP.join((self.min_field_name, 'lte' if self.include_boundaries else 'lt')): value,
        })
        if not self.in_range:
            condition.negate()
        return condition
