# -*- coding: utf-8 -*-


class QuerySetOperation(object):
    """Base class for operations that allow to perform in-place modifications of querysets."""

    def __call__(self, queryset):
        """
        Execute this operation on the given queryset if applicable.

        :param queryset: The queryset to modify.
        :type queryset: queryable_properties.managers.QueryablePropertiesQuerySet
        """
        if self.is_applicable(queryset):
            self.execute(queryset)

    def is_applicable(self, queryset):  # pragma: no cover
        """
        Check whether this operation can be executed on the given queryset.

        :param queryset: The queryset to check.
        :type queryset: queryable_properties.managers.QueryablePropertiesQuerySet
        :return: True if the operation can be executed; otherwise False.
        :rtype: bool
        """
        raise NotImplementedError()

    def execute(self, queryset):  # pragma: no cover
        """
        Execute this operation on the given queryset.

        The queryset and/or its query must be modified in-place.

        :param queryset: The queryset to modify.
        :type queryset: queryable_properties.managers.QueryablePropertiesQuerySet
        """
        raise NotImplementedError()


class SelectRelatedOperation(QuerySetOperation):
    """A queryset operation that potentially leads to the selection of related objects."""

    def __init__(self, *fields):
        """
        Initialize a new select related operation.

        :param str fields: The related names of the objects to select. Must be
                           compatible with ``select_related`` calls.
        """
        self.fields = fields

    def is_applicable(self, queryset):
        return bool(self.fields) and queryset.query.select_related is not True

    def execute(self, queryset):
        queryset.query.add_select_related(self.fields)
