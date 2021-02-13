# -*- coding: utf-8 -*-

from django.contrib.admin import ModelAdmin, StackedInline, TabularInline

from ..compat import admin_validation, chain_queryset
from ..exceptions import QueryablePropertyError
from ..managers import QueryablePropertiesQuerySetMixin
from .checks import QueryablePropertiesChecksMixin
from .filters import QueryablePropertyField


class QueryablePropertiesAdminMixin(object):

    list_select_properties = None

    @classmethod
    def validate(cls, model):
        cls._ensure_property_checks()
        return super(QueryablePropertiesAdminMixin, cls).validate(model)

    def check(self, model=None, **kwargs):
        if model:
            kwargs['model'] = model
        self._ensure_property_checks(self)
        return super(QueryablePropertiesAdminMixin, self).check(**kwargs)

    if getattr(getattr(ModelAdmin, 'check', None), '__self__', None):
        # In old Django versions, check was a classmethod.
        check = classmethod(check)

    @classmethod
    def _ensure_property_checks(cls, obj=None):
        obj = obj or cls
        # Dynamically add a mixin that handles queryable properties into the
        # admin's checks/validation class.
        for attr_name in ('checks_class', 'validator_class', 'default_validator_class'):
            checks_class = getattr(obj, attr_name, None)
            if checks_class and not issubclass(checks_class, QueryablePropertiesChecksMixin):
                class_name = 'QueryableProperties' + checks_class.__name__
                setattr(obj, attr_name, QueryablePropertiesChecksMixin.mix_with_class(checks_class, class_name))

    def get_queryset(self, request):
        queryset = super(QueryablePropertiesAdminMixin, self).get_queryset(request)
        # Make sure to use a queryset with queryable properties features.
        if not isinstance(queryset, QueryablePropertiesQuerySetMixin):
            queryset = chain_queryset(queryset)
            QueryablePropertiesQuerySetMixin.inject_into_object(queryset)
        # Apply list_select_properties.
        list_select_properties = self.get_list_select_properties()
        if list_select_properties:
            queryset = queryset.select_properties(*list_select_properties)
        return queryset

    def get_list_filter(self, request):
        list_filter = super(QueryablePropertiesAdminMixin, self).get_list_filter(request)
        expanded_filters = []
        for item in list_filter:
            if not callable(item):
                if isinstance(item, (tuple, list)):
                    field_name, filter_class = item
                else:
                    field_name, filter_class = item, None
                try:
                    item = QueryablePropertyField(self, request, field_name).create_list_filter(filter_class)
                except QueryablePropertyError:
                    pass
            expanded_filters.append(item)
        return expanded_filters

    def get_list_select_properties(self):
        return self.list_select_properties


class QueryablePropertiesAdmin(QueryablePropertiesAdminMixin, ModelAdmin):

    pass


class QueryablePropertiesStackedInline(QueryablePropertiesAdminMixin, StackedInline):

    pass


class QueryablePropertiesTabularInline(QueryablePropertiesAdminMixin, TabularInline):

    pass


# In very old django versions, the admin validation happens in one big function
# that cannot really be extended well. Therefore, the Django module will be
# monkeypatched in order to allow the queryable properties validation to take
# effect.
django_validate = getattr(admin_validation, 'validate', None)
if django_validate:
    def validate(cls, model):
        if issubclass(cls, QueryablePropertiesAdminMixin):
            cls = QueryablePropertiesChecksMixin()._validate_queryable_properties(cls, model)
        django_validate(cls, model)

    admin_validation.validate = validate
