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
        for attr_name, validator_class in (
            ('validator_class', cls.validator_class),
            ('default_validator_class', getattr(cls, 'default_validator_class', None)),
        ):
            if validator_class and not issubclass(validator_class, QueryablePropertiesChecksMixin):
                class_name = 'QueryableProperties' + validator_class.__name__
                setattr(cls, attr_name, QueryablePropertiesChecksMixin.mix_with_class(validator_class, class_name))
        return super(QueryablePropertiesAdminMixin, cls).validate(model)

    def check(self, **kwargs):  # TODO: Django 1.8 special case
        # Dynamically add a mixin that handles queryable properties into the
        # admin's checks class.
        if not issubclass(self.checks_class, QueryablePropertiesChecksMixin):
            class_name = 'QueryableProperties' + self.checks_class.__name__
            self.checks_class = QueryablePropertiesChecksMixin.mix_with_class(self.checks_class, class_name)
        return super(QueryablePropertiesAdminMixin, self).check(**kwargs)

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
