# -*- coding: utf-8 -*-
import six
from django.contrib.admin import ModelAdmin, StackedInline, TabularInline
from django.db.models import F

from ..compat import admin_validation, compat_call
from ..exceptions import QueryablePropertyError
from ..managers import QueryablePropertiesQuerySetMixin
from ..utils.deprecation import deprecated
from ..utils.internal import InjectableMixin, QueryPath, resolve_queryable_property
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
            if checks_class:
                class_name = 'QueryableProperties' + checks_class.__name__
                setattr(obj, attr_name, QueryablePropertiesChecksMixin.mix_with_class(checks_class, class_name))

    def get_queryset(self, request):
        # Make sure to use a queryset with queryable properties features.
        queryset = QueryablePropertiesQuerySetMixin.apply_to(
            compat_call(super(QueryablePropertiesAdminMixin, self), ('get_queryset', 'queryset'), request))
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

    def get_changelist(self, request, **kwargs):
        # Dynamically add a mixin that handles queryable properties into the
        # admin's changelist class.
        cls = super(QueryablePropertiesAdminMixin, self).get_changelist(request, **kwargs)
        return QueryablePropertiesChangeListMixin.mix_with_class(cls, 'QueryableProperties' + cls.__name__)

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

    @deprecated(hint='Calls are no longer required and may simply be removed without replacement.')
    def process_queryable_property_filters(self, list_filter):
        """
        Process a sequence of list filters to create a new sequence in which
        queryable property references are replaced with custom callables that
        make them compatible with Django's filter workflow.

        :param collections.Sequence list_filter: The list filter sequence.
        :return: The processed list filter sequence.
        :rtype: list
        """
        return list_filter


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


class QueryablePropertiesChangeListMixin(InjectableMixin):

    def __init__(self, request, model, list_display, list_display_links, list_filter, date_hierarchy, search_fields,
                 list_select_related, list_per_page, list_max_show_all, list_editable, model_admin, *args, **kwargs):
        # Process related queryable properties to be used as display columns by
        # replacing their references with custom callables that make them
        # compatible with Django's list_display handling.
        self._related_display_properties = {}
        processed_display = []
        for item in list_display:
            if not callable(item):
                property_ref = resolve_queryable_property(model, QueryPath(item))[0]
                if property_ref and property_ref.relation_path:
                    full_name = property_ref.full_path.as_str()
                    item = lambda obj: getattr(obj, full_name)
                    item.short_description = property_ref.property.short_description
                    item.admin_order_field = full_name
                    self._related_display_properties[full_name] = item
            processed_display.append(item)

        # Process queryable properties to be used as filters by replacing their
        # references with custom callables that make them compatible with
        # Django's filter workflow.
        processed_filters = []
        for item in list_filter:
            if not callable(item):
                if isinstance(item, (tuple, list)):
                    field_name, filter_class = item
                else:
                    field_name, filter_class = item, None
                try:
                    item = QueryablePropertyField(model_admin, QueryPath(field_name)).get_filter_creator(filter_class)
                except QueryablePropertyError:
                    pass
            processed_filters.append(item)

        super(QueryablePropertiesChangeListMixin, self).__init__(request, model, processed_display, list_display_links,
                                                                 processed_filters, date_hierarchy, search_fields,
                                                                 list_select_related, list_per_page, list_max_show_all,
                                                                 list_editable, model_admin, *args, **kwargs)

        list_display_refs = []
        if self.list_display_links:
            self.list_display_links = list(self.list_display_links)
            list_display_refs.append(self.list_display_links)
        if hasattr(self, 'sortable_by') and self.sortable_by:
            self.sortable_by = list(self.sortable_by)
            list_display_refs.append(self.sortable_by)
        for list_display_ref in list_display_refs:
            for item, replacement in six.iteritems(self._related_display_properties):
                if item in list_display_ref:
                    list_display_ref.remove(item)
                    list_display_ref.append(replacement)

    def get_queryset(self, *args, **kwargs):
        if self._related_display_properties:
            self.root_queryset = self.root_queryset.annotate(**{
                item: F(item) for item in self._related_display_properties
            })
        return super(QueryablePropertiesChangeListMixin, self).get_queryset(*args, **kwargs)


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
