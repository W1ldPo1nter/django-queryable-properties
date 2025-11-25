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
        """
        Initialize a new property that allows to determine the content type of
        model instances.

        :keyword depth: The maximum depth of the inheritance hierarchy to
                        follow. Instances of model classes below this maximum
                        depth will be treated as objects of the maximum depth.
                        If not provided, no maximum depth will be enforced.
        :keyword field_names: The names of the fields that should be queried
                              for content type objects. Fields not present in
                              this sequence will be deferred. If not provided,
                              all concrete content type fields will be queried.
        """
        kwargs['model'] = 'contenttypes.ContentType'
        # Set the _inner_queryset attribute as well as SubqueryObjectProperty
        # will pass it on to the individual field properties.
        kwargs['queryset'] = self._get_inner_queryset
        super(ContentTypeProperty, self).__init__(**kwargs)

    def _get_value_for_model(self, model):
        return model._meta.label_lower

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
