# -*- coding: utf-8 -*-

from django.contrib.admin import ModelAdmin, StackedInline, TabularInline

from ..compat import ADMIN_QUERYSET_METHOD_NAME, admin_validation, chain_queryset
from ..exceptions import QueryablePropertyError
from ..managers import QueryablePropertiesQuerySetMixin
from .checks import QueryablePropertiesChecksMixin
from .filters import QueryablePropertyField

__all__ = [
    'QueryablePropertiesAdmin',
    'QueryablePropertiesAdminMixin',
    'QueryablePropertiesStackedInline',
    'QueryablePropertiesTabularInline',
]


class QueryablePropertiesAdminMixin(object):
    """
    A mixin for admin classes including inlines that allows to use queryable
    properties in various admin features.
    """

    list_select_properties = ()
    """A sequence of queryable property names that should be selected."""

    def __init__(self, *args, **kwargs):
        super(QueryablePropertiesAdminMixin, self).__init__(*args, **kwargs)
        if hasattr(self, 'list_filter') and not hasattr(ModelAdmin, 'get_list_filter'):  # pragma: no cover
            # In very old Django versions, there was no get_list_filter method,
            # therefore the processed queryable property filters must be stored
            # directly in the list_filter attribute.
            self.list_filter = self.process_queryable_property_filters(self.list_filter)

    @classmethod
    def validate(cls, model):  # pragma: no cover
        cls._ensure_queryable_property_checks()
        return super(QueryablePropertiesAdminMixin, cls).validate(model)

    def check(self, *args, **kwargs):
        self._ensure_queryable_property_checks(self)
        return super(QueryablePropertiesAdminMixin, self).check(*args, **kwargs)

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
            if checks_class and not issubclass(checks_class, QueryablePropertiesChecksMixin):
                class_name = 'QueryableProperties' + checks_class.__name__
                setattr(obj, attr_name, QueryablePropertiesChecksMixin.mix_with_class(checks_class, class_name))

    def get_queryset(self, request):
        # The base method has different names in different Django versions (see
        # comment on the constant definition).
        base_method = getattr(super(QueryablePropertiesAdminMixin, self), ADMIN_QUERYSET_METHOD_NAME)
        queryset = base_method(request)
        # Make sure to use a queryset with queryable properties features.
        if not isinstance(queryset, QueryablePropertiesQuerySetMixin):
            queryset = chain_queryset(queryset)
            QueryablePropertiesQuerySetMixin.inject_into_object(queryset)
        # Apply list_select_properties.
        list_select_properties = self.get_list_select_properties(request)
        if list_select_properties:
            queryset = queryset.select_properties(*list_select_properties)
        return queryset

    def queryset(self, request):  # pragma: no cover
        # Same as get_queryset, but for very old Django versions. Simply
        # delegate to need_having, which is aware of the different methods in
        # different versions and therefore calls the correct super methods if
        # necessary.
        return self.get_queryset(request)

    def get_list_select_properties(self, request):
        """
        Wrapper around the `list_select_properties` attribute that allows to
        dynamically create the list of queryable property names to select based
        on the given request.

        :param django.http.HttpRequest request: The request to the admin.
        :return: A sequence of queryable property names to select.
        :rtype: collections.Sequence[str]
        """
        return self.list_select_properties

    def get_list_filter(self, request):
        list_filter = super(QueryablePropertiesAdminMixin, self).get_list_filter(request)
        return self.process_queryable_property_filters(list_filter)

    def process_queryable_property_filters(self, list_filter):
        """
        Process a sequence of list filters to create a new sequence in which
        queryable property references are replaced with custom callables that
        make them compatible with Django's filter workflow.

        :param collections.Sequence list_filter: The list filter sequence.
        :return: The processed list filter sequence.
        :rtype: collections.Sequence
        """
        processed_filters = []
        for item in list_filter:
            if not callable(item):
                if isinstance(item, (tuple, list)):
                    field_name, filter_class = item
                else:
                    field_name, filter_class = item, None
                try:
                    item = QueryablePropertyField(self, field_name).get_filter_creator(filter_class)
                except QueryablePropertyError:
                    pass
            processed_filters.append(item)
        return processed_filters


class QueryablePropertiesAdmin(QueryablePropertiesAdminMixin, ModelAdmin):
    """
    Base class for admin classes which allows to use queryable properties in
    various admin features.

    Intended to be used in place of Django's regular `ModelAdmin` class.
    """


class QueryablePropertiesStackedInline(QueryablePropertiesAdminMixin, StackedInline):
    """
    Base class for stacked inline classes which allows to use queryable
    properties in various admin features.

    Intended to be used in place of Django's regular `StackedInline` class.
    """


class QueryablePropertiesTabularInline(QueryablePropertiesAdminMixin, TabularInline):
    """
    Base class for tabular inline classes which allows to use queryable
    properties in various admin features.

    Intended to be used in place of Django's regular `TabularInline` class.
    """


# In very old django versions, the admin validation happens in one big function
# that cannot really be extended well. Therefore, the Django module will be
# monkeypatched in order to allow the queryable properties validation to take
# effect.
django_validate = getattr(admin_validation, 'validate', None)
django_validate_inline = getattr(admin_validation, 'validate_inline', None)

if django_validate:  # pragma: no cover
    def validate(cls, model):
        if issubclass(cls, QueryablePropertiesAdminMixin):
            cls = QueryablePropertiesChecksMixin()._validate_queryable_properties(cls, model)
        django_validate(cls, model)

    admin_validation.validate = validate

if django_validate_inline:  # pragma: no cover
    def validate_inline(cls, parent, parent_model):
        if issubclass(cls, QueryablePropertiesAdminMixin):
            cls = QueryablePropertiesChecksMixin()._validate_queryable_properties(cls, cls.model)
        django_validate_inline(cls, parent, parent_model)

    admin_validation.validate_inline = validate_inline
