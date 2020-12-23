Annotation-based properties
===========================

There are various scenarios where even the getter of a (queryable) property must perform a database query to provide
its value, e.g. when the property:

- is based on an aggregate,
- checks for the existence of related/other objects in the database,
- loads a field value from anywhere else in the database via a custom subquery,
- etc.

Since most, if not all, of these cases can be expressed using queryset annotations, this allows the use of
:ref:`annotations:Annotatable properties` to implement a corresponding queryable property.
If the getter of a property would require to perform a query anyways, one could simply reuse the annotation to
implement the getter to achieve both features in a DRY manner.
*django-queryable-properties* therefore offers a dedicated option that allows to implement annotation-based properties
that use the annotater implementation to provide the getter value - this allows to implement a queryable property that
has a functional getter and allows filtering and the use all annotation-based queryset features while only implementing
the annotation.

.. note::
   One should only use annotation-based properties whenever the getter would need to perform a query anyways.
   Whenever the getter could be implemented without performing extra queries, it should be implemented manually as
   the query-less implementation is likely more performant.

Implementation
--------------

To provide a realisticc example, let's implement a property that provides the number of versions that is defined for
an application, similar to the example in :ref:`annotations:Regarding aggregate annotations across relations`.

The decorator-based approach for an annotation-based property looks slightly different since the `queryable_property`
decorator is normally used for the getter, but the goal of annotation-based properties is to avoid having to manually
implement a getter.
The ``queryable_property`` decorator therefore accepts an ``annotation_based`` argument for this use case - if it is
set to ``True``, the decorator expects the annotation function (that is usually decorated with
``@<property_name>.annotater`` - see :ref:`annotations:Implementation`) as the decorated function instead of the getter
function.

.. code-block:: python

    from django.db.models import Count, Model, Value
    from queryable_properties.properties import queryable_property


    class ApplicationVersion(Model):
        ...

        @queryable_property(annotation_based=True)
        @classmethod
        def version_count(cls):
            """Return the number of versions that exist for this application."""
            return Count('versions')

.. note::
   The ``classmethod`` decorator is not required, but makes the function look more natural since it takes the model
   class as its first argument.

The class-based approach looks a lot like a regular annotatable property - it simply uses the ``AnnotationGetterMixin``
instead of the ``AnnotationMixin``, which already implements ``get_value`` to be based on the annotation.

.. code-block:: python

    from django.db.models import Count, Value
    from queryable_properties.properties import AnnotationGetterMixin, QueryableProperty


    class VersionCountProperty(AnnotationGetterMixin, QueryableProperty):

        def get_annotation(self, cls):
            return Count('versions')

About the ``AnnotationGetterMixin``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :class:`queryable_properties.properties.AnnotationGetterMixin` is the core part of the option to implement
annotation-based properties.
It is used explicitly in the class-based approach, but also automatically added to properties defined using the
decorator-based approach whenever the ``annotation_based`` argument is set to ``True``.
This mixin is based on the ``AnnotationMixin``, which means that all notes described in
:ref:`annotations:The \`\`AnnotationMixin\`\` and custom filter implementations` apply here as well.

The main addition provided by the ``AnnotationGetterMixin`` is the provided implementation of the ``get_value`` method
to implement the getter.
This getter builds a ``DISTINCT`` queryset using the base manager (``_base_manager``) of the object the property is
accessed on, filters it to only that object via its primary key, adds the annotation and retrieves only the annotation
value via ``values_list`` and ``get``.
The getter may therefore raise ``MultipleObjectsReturned`` exceptions if somehow more than one row is returned or
``DoesNotExist`` exceptions if no row can be found (e.g. when accessing the property on an object that is not yet saved
to the database).

Due to the performed queries, the getters of annotation-based properties can be a prime use case for a
:ref:`standard_features:Cached getter`.
Because of this, the ``AnnotationGetterMixin`` also adds the ``cached`` argument to the initializer (``__init__``) of
the classes that use it (which is only relevant for the class-based approach).
This means that objects of the property class can be individually flagged as cached properties.
The ``VersionCountProperty`` example above could therefore be used in the following ways:

.. code-block:: python

    class ApplicationVersion(Model):
        ...

        version_count = VersionCountProperty()
        # ... or ...
        version_count = VersionCountProperty(cached=False)
        # ... or ...
        version_count = VersionCountProperty(cached=True)

The default value for this ``cached`` argument is ``None``, which is interpreted as "use the default value".
This allows to retain the ability to set the ``cached`` flag as a class attribute as well, which then provides this
default value.
