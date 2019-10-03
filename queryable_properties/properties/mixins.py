# encoding: utf-8

from django.db.models import Q

from ..compat import LOOKUP_SEP
from ..utils import InjectableMixin


class SetterMixin(object):
    """
    A mixin for queryable properties that also define a setter.
    """

    def set_value(self, obj, value):  # pragma: no cover
        """
        Setter method for the queryable property, which will be called when the
        property is write-accessed.

        :param django.db.models.Model obj: The object on which the property was
                                           accessed.
        :param value: The value to set.
        """
        raise NotImplementedError()


class AnnotationMixin(InjectableMixin):
    """
    A mixin for queryable properties that allow to add an annotation to
    represent them to querysets.
    """

    # Avoid overriding the __reduce__ implementation of queryable properties.
    _dynamic_pickling = False

    filter_requires_annotation = True

    def get_annotation(self, cls):  # pragma: no cover
        """
        Construct an annotation representing this property that can be added
        to querysets of the model associated with this property.

        :param type cls: The model class of which a queryset should be
                         annotated.
        :return: An annotation object.
        """
        raise NotImplementedError()

    def get_filter(self, cls, lookup, value):
        # Since annotations can be filtered like regular fields, a Q object
        # that simply passes the filter through can be used.
        return Q(**{LOOKUP_SEP.join((self.name, lookup)): value})


class UpdateMixin(object):
    """
    A mixin for queryable properties that allow to use themselves in update
    queries.
    """

    def get_update_kwargs(self, cls, value):  # pragma: no cover
        """
        Resolve an update keyword argument for this property into the actual
        keyword arguments to emulate an update using this property.

        :param type cls: The model class of which an update query should be
                         performed.
        :param value: The value passed to the update call for this property.
        :return: The actual keyword arguments to set in the update call instead
                 of the given one.
        :rtype: dict
        """
        raise NotImplementedError()
