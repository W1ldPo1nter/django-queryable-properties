# -*- coding: utf-8 -*-
from django.db.models import CharField

from .mixins import InheritanceMixin
from .subquery import SubqueryObjectProperty


class ContentTypeProperty(InheritanceMixin, SubqueryObjectProperty):
    """
    A property that allows to determine the content type of model instances.
    """

    _inheritance_output_field = CharField()

    def __init__(self, **kwargs):
        kwargs['model'] = 'contenttypes.ContentType'
        # Set the _inner_queryset attribute as well as SubqueryObjectProperty
        # will pass it on to the individual field properties.
        kwargs['queryset'] = self._get_inner_queryset
        super(ContentTypeProperty, self).__init__(**kwargs)

    def _get_value_for_model(self, model):
        return '.'.join((model._meta.app_label, model._meta.model_name))

    def _get_condition_for_model(self, model, query_path):
        from django.db.models import OuterRef
        from django.db.models.lookups import IsNull

        return IsNull(OuterRef(query_path.as_str()), False)

    def _get_inner_queryset(self, model):
        from django.db.models import Value
        from django.db.models.functions import Concat
        from django.db.models.lookups import Exact

        return self._subquery_model.objects.filter(Exact(
            Concat('app_label', Value('.'), 'model'),
            self._build_case_expression(model),
        ))
