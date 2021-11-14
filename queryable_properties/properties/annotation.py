# -*- coding: utf-8 -*-

from django.db.models import Q

from ..utils.internal import QueryPath
from .base import QueryableProperty
from .mixins import AnnotationGetterMixin, BooleanMixin


class AnnotationProperty(AnnotationGetterMixin, QueryableProperty):
    """
    A property that is based on a static annotation that is even used to
    provide getter values.
    """

    def __init__(self, annotation, **kwargs):
        """
        Initialize a new property that gets its value by retrieving an
        annotated value from the database.

        :param annotation: The static annotation to use to determine the value
                           of this property.
        """
        super(AnnotationProperty, self).__init__(**kwargs)
        self.annotation = annotation

    def get_annotation(self, cls):
        return self.annotation


class AggregateProperty(AnnotationProperty):
    """
    A property that is based on an aggregate that is used to provide both
    queryset annotations as well as getter values.
    """

    def __init__(self, aggregate, **kwargs):
        """
        Initialize a new property that gets its value by retrieving an
        aggregated value from the database.

        :param django.db.models.Aggregate aggregate: The aggregate to use to
                                                     determine the value of
                                                     this property.
        """
        super(AggregateProperty, self).__init__(aggregate, **kwargs)

    def get_value(self, obj):
        return self.get_queryset_for_object(obj).aggregate(**{self.name: self.annotation})[self.name]


class RelatedExistenceCheckProperty(BooleanMixin, AnnotationGetterMixin, QueryableProperty):
    """
    A property that checks whether related objects to the one that uses the
    property exist in the database and returns a corresponding boolean value.

    Supports queryset filtering and ``CASE``/``WHEN``-based annotating.
    """

    def __init__(self, relation_path, negated=False, **kwargs):
        """
        Initialize a new property that checks for the existence of related
        objects.

        :param str relation_path: The path to the object/field whose existence
                                  is to be checked. May contain the lookup
                                  separator (``__``) to check for more remote
                                  relations.
        """
        super(RelatedExistenceCheckProperty, self).__init__(**kwargs)
        self.query_path = QueryPath(relation_path) + 'isnull'
        self.negated = negated

    @property
    def _base_condition(self):
        """
        Return the base condition for the existence check that can be applied to a queryset of the model this property
        is defined on for the positive (existence check rather than non-existence check) case.

        :return: The base condition for this property.
        :rtype: django.db.models.Q
        """
        return self.query_path.build_filter(False)

    def get_value(self, obj):
        condition = self._base_condition
        if self.negated:
            condition.negate()
        return self.get_queryset_for_object(obj).filter(condition).exists()

    def _get_condition(self, cls):
        # Perform the filtering via a subquery to avoid any side-effects that may be introduced by JOINs.
        condition = Q(pk__in=self.get_queryset(cls).filter(self._base_condition))
        if self.negated:
            condition.negate()
        return condition
