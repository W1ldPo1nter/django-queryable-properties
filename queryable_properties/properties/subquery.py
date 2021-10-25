# -*- coding: utf-8 -*-

from .base import QueryableProperty
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

    def _build_subquery(self, queryset):
        from django.db.models import Subquery

        return Subquery(queryset.values(self.field_name)[:1], output_field=self.output_field)


class SubqueryExistenceCheckProperty(SubqueryMixin, QueryableProperty):
    """
    A property that checks whether or not certain objects exist in the database
    using a custom subquery.
    """

    def __init__(self, queryset, negated=False, **kwargs):
        """
        Initialize a new property that checks for the existence of database
        records using a custom subquery.

        :param queryset: The internal queryset to use as the subquery or a
                         callable without arguments that generates the internal
                         queryset.
        :type queryset: django.db.models.QuerySet | function
        :param bool negated: Whether or not to negate the ``EXISTS`` subquery
                             (i.e. the property will return ``True`` if no
                             objects exist when using ``negated=True``).
        """
        self.negated = negated
        super(SubqueryExistenceCheckProperty, self).__init__(queryset, **kwargs)

    def _build_subquery(self, queryset):
        from django.db.models import Exists

        return Exists(queryset, negated=self.negated)
