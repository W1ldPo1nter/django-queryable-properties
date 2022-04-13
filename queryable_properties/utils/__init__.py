# encoding: utf-8

from collections import defaultdict

import six

from .internal import MISSING_OBJECT, ModelAttributeGetter, QueryPath, get_queryable_property_descriptor

__all__ = ('MISSING_OBJECT', 'get_queryable_property', 'prefetch_queryable_properties', 'reset_queryable_property')


def get_queryable_property(model, name):
    """
    Retrieve the :class:`queryable_properties.properties.QueryableProperty`
    object with the given attribute name from the given model class or raise
    an error if no queryable property with that name exists on the model class.

    :param type model: The model class to retrieve the property object from.
    :param str name: The name of the property to retrieve.
    :return: The queryable property.
    :rtype: queryable_properties.properties.QueryableProperty
    """
    return get_queryable_property_descriptor(model, name).prop


get_queryable_property.__safe_for_unpickling__ = True


def reset_queryable_property(obj, name):
    """
    Reset the cached value of the queryable property with the given name on the
    given model instance. Read-accessing the property on this model instance at
    a later point will therefore execute the property's getter again.

    :param django.db.models.Model obj: The model instance to reset the cached
                                       value on.
    :param str name: The name of the queryable property.
    """
    descriptor = get_queryable_property_descriptor(obj.__class__, name)
    descriptor.clear_cached_value(obj)


def prefetch_queryable_properties(model_instances, *property_paths):
    """
    Populate the queryable property caches for a list of model instances based
    on the given property paths.

    :param model_instances: The model instances to prefetch the property values
                            for. The instances may be objects of different
                            models as long as the given property paths are
                            valid for all of them.
    :type model_instances: collections.Sequence
    :param str property_paths: The paths to the properties whose values should
                               be fetched, which are need to be annotatable.
                               The paths may contain the lookup separator to
                               fetch values of properties on related objects
                               (make sure that the related objects are already
                               prefetched to avoid additional queries).
    """
    from ..managers import QueryablePropertiesQuerySetMixin

    # Since the model instances may be of different types and the property
    # paths may refer to properties on related objects, the first step is
    # figuring out which exact properties need to be queried and for which
    # models a query needs to be performed.
    properties_by_model = defaultdict(lambda: defaultdict(list))
    pks_by_model = defaultdict(set)
    for path in property_paths:
        query_path = QueryPath(path)
        getter = ModelAttributeGetter(query_path[:-1])
        for instance in model_instances:
            for resolved_instance in getter.get_values(instance):
                if resolved_instance is not None:
                    properties_by_model[resolved_instance.__class__][query_path[-1]].append(resolved_instance)
                    pks_by_model[resolved_instance.__class__].add(resolved_instance.pk)

    # Perform a single query for each model, querying all properties that have
    # been requested for that model (be it directly or via relations).
    for model, property_mappings in six.iteritems(properties_by_model):
        queryset = QueryablePropertiesQuerySetMixin.inject_into_object(model._base_manager.all())
        queryset = queryset.filter(pk__in=pks_by_model[model]).select_properties(*property_mappings)
        for result in queryset.values('pk', *property_mappings):
            pk = result.pop('pk')
            for property_name, value in six.iteritems(result):
                descriptor = get_queryable_property_descriptor(model, property_name)
                for instance in property_mappings[property_name]:
                    # Only populate the cache for the concrete objects the
                    # property values were requested for (different relations
                    # may lead to the same model).
                    if instance.pk == pk:
                        descriptor.set_cached_value(instance, value)
