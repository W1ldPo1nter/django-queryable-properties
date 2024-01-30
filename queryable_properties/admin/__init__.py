from django.contrib.admin import ModelAdmin, StackedInline, TabularInline

from ..exceptions import QueryablePropertyError
from ..managers import QueryablePropertiesQuerySetMixin
from ..utils.internal import QueryPath
from .checks import QueryablePropertiesChecksMixin
from .filters import QueryablePropertyField

__all__ = [
    'QueryablePropertiesAdmin',
    'QueryablePropertiesAdminMixin',
    'QueryablePropertiesStackedInline',
    'QueryablePropertiesTabularInline',
]


class QueryablePropertiesAdminMixin:
    """
    A mixin for admin classes including inlines that allows to use queryable
    properties in various admin features.
    """

    list_select_properties = ()
    """A sequence of queryable property names that should be selected."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, 'list_filter') and not hasattr(ModelAdmin, 'get_list_filter'):  # pragma: no cover
            # In very old Django versions, there was no get_list_filter method,
            # therefore the processed queryable property filters must be stored
            # directly in the list_filter attribute.
            self.list_filter = self.process_queryable_property_filters(self.list_filter)

    @classmethod
    def validate(cls, model):  # pragma: no cover
        cls._ensure_queryable_property_checks()
        return super().validate(model)

    def check(self, *args, **kwargs):
        self._ensure_queryable_property_checks(self)
        return super().check(*args, **kwargs)

    if getattr(getattr(ModelAdmin, 'check', None), '__self__', None):  # pragma: no cover
        # In old Django versions, check was a classmethod.
        check = classmethod(check)

    @classmethod
    def _ensure_queryable_property_checks(cls, obj=None):
        """
        Make sure that the queryable properties admin check extensions are used
        to avoid errors due to Django's default validation, which would treat
        queryable property names as invalid.

        :param obj: The (optional) model admin instance to ensure the queryable
                    property checks for. If not provided, they are ensured for
                    the current class instead.
        :type obj: ModelAdmin | None
        """
        obj = obj or cls
        # Dynamically add a mixin that handles queryable properties into the
        # admin's checks/validation class.
        for attr_name in ('checks_class', 'validator_class', 'default_validator_class'):
            checks_class = getattr(obj, attr_name, None)
            if checks_class:
                class_name = 'QueryableProperties' + checks_class.__name__
                setattr(obj, attr_name, QueryablePropertiesChecksMixin.mix_with_class(checks_class, class_name))

    def get_queryset(self, request):
        # Make sure to use a queryset with queryable properties features.
        queryset = QueryablePropertiesQuerySetMixin.apply_to(super().get_queryset(request))
        # Apply list_select_properties.
        list_select_properties = self.get_list_select_properties(request)
        if list_select_properties:
            queryset = queryset.select_properties(*list_select_properties)
        return queryset

    def queryset(self, request):  # pragma: no cover
        # Same as get_queryset, but for very old Django versions. Simply
        # delegate to get_queryset, which is aware of the different methods in
        # different versions and therefore calls the correct super methods if
        # necessary.
        return self.get_queryset(request)

    def get_list_select_properties(self, request):
        """
        Wrapper around the ``list_select_properties`` attribute that allows to
        dynamically create the list of queryable property names to select based
        on the given request.

        :param django.http.HttpRequest request: The request to the admin.
        :return: A sequence of queryable property names to select.
        :rtype: collections.Sequence[str]
        """
        return self.list_select_properties

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        return self.process_queryable_property_filters(list_filter)

    def process_queryable_property_filters(self, list_filter):
        """
        Process a sequence of list filters to create a new sequence in which
        queryable property references are replaced with custom callables that
        make them compatible with Django's filter workflow.

        :param collections.Sequence list_filter: The list filter sequence.
        :return: The processed list filter sequence.
        :rtype: list
        """
        processed_filters = []
        for item in list_filter:
            if not callable(item):
                if isinstance(item, (tuple, list)):
                    field_name, filter_class = item
                else:
                    field_name, filter_class = item, None
                try:
                    item = QueryablePropertyField(self, QueryPath(field_name)).get_filter_creator(filter_class)
                except QueryablePropertyError:
                    pass
            processed_filters.append(item)
        return processed_filters


class QueryablePropertiesAdmin(QueryablePropertiesAdminMixin, ModelAdmin):
    """
    Base class for admin classes which allows to use queryable properties in
    various admin features.

    Intended to be used in place of Django's regular ``ModelAdmin`` class.
    """


class QueryablePropertiesStackedInline(QueryablePropertiesAdminMixin, StackedInline):
    """
    Base class for stacked inline classes which allows to use queryable
    properties in various admin features.

    Intended to be used in place of Django's regular ``StackedInline`` class.
    """


class QueryablePropertiesTabularInline(QueryablePropertiesAdminMixin, TabularInline):
    """
    Base class for tabular inline classes which allows to use queryable
    properties in various admin features.

    Intended to be used in place of Django's regular ``TabularInline`` class.
    """


django_validate = None
django_validate_inline = None
