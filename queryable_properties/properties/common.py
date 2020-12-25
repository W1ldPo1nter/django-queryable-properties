# encoding: utf-8

import operator

from django.db.models import BooleanField

from ..utils import MISSING_OBJECT, ModelAttributeGetter
from .base import QueryableProperty
from .mixins import AnnotationGetterMixin, AnnotationMixin, boolean_filter, LookupFilterMixin


class BooleanMixin(LookupFilterMixin):
    """
    Internal mixin class for common properties that return boolean values,
    which is intended to be used in conjunction with one of the annotation
    mixins.
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


class ValueCheckProperty(BooleanMixin, AnnotationMixin, QueryableProperty):
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


class RangeCheckProperty(BooleanMixin, AnnotationMixin, QueryableProperty):
    """
    A property that checks if a static or dynamic value is contained in a range
    expressed by two field values and returns a corresponding boolean value.

    Supports queryset filtering and CASE/WHEN-based annotating.
    """

    def __init__(self, min_attribute_path, max_attribute_path, value, include_boundaries=True, in_range=True,
                 include_missing=False):
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
                                       value raises an ObjectDoesNotExist
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
                              `True` if the value is in range (`in_range=True`)
                              or if it is out of the range (`in_range=False`).
                              This also affects the impact of the
                              `include_boundaries` and `include_missing`
                              parameters.
        :param bool include_missing: Whether or not a missing value is
                                     considered a part of the range (see the
                                     description of `min_attribute_path`).
                                     Useful e.g. for nullable fields.
        """
        self.min_attribute_getter = ModelAttributeGetter(min_attribute_path)
        self.max_attribute_getter = ModelAttributeGetter(max_attribute_path)
        self.value = value
        self.include_boundaries = include_boundaries
        self.in_range = in_range
        self.include_missing = include_missing
        super(RangeCheckProperty, self).__init__()

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

    def _get_condition(self):
        value = self.final_value
        lower_condition = self.min_attribute_getter.build_filter('lte' if self.include_boundaries else 'lt', value)
        upper_condition = self.max_attribute_getter.build_filter('gte' if self.include_boundaries else 'gt', value)
        if self.include_missing:
            lower_condition |= self.min_attribute_getter.build_filter('isnull', True)
            upper_condition |= self.max_attribute_getter.build_filter('isnull', True)
        if not self.in_range:
            return ~lower_condition | ~upper_condition
        return lower_condition & upper_condition


class AnnotationProperty(AnnotationGetterMixin, QueryableProperty):
    """
    A property that is based on a static annotation that is even used to
    provide getter values.
    """

    def __init__(self, annotation, cached=None):
        """
        Initialize a new property that gets its value by retrieving an
        annotated value from the database.

        :param annotation: The static annotation to use to determine the value
                           of this property.
        :param bool cached: Whether or not this property should use a cached
                            getter. If the property is not cached, the getter
                            will perform the corresponding annotated query on
                            every access.
        """
        super(AnnotationProperty, self).__init__(cached)
        self.annotation = annotation

    def get_annotation(self, cls):
        return self.annotation


class AggregateProperty(AnnotationProperty):
    """
    A property that is based on an aggregate that is used to provide both
    queryset annotations as well as getter values.
    """

    def __init__(self, aggregate, cached=None):
        """
        Initialize a new property that gets its value by retrieving an
        aggregated value from the database.

        :param django.db.models.Aggregate aggregate: The aggregate to use to
                                                     determine the value of
                                                     this property.
        :param bool cached: Whether or not this property should use a cached
                            getter. If the property is not cached, the getter
                            will perform the corresponding aggregate query on
                            every access.
        """
        super(AggregateProperty, self).__init__(aggregate, cached)

    def get_value(self, obj):
        return self.get_queryset(obj).aggregate(**{self.name: self.annotation})[self.name]
