Simple annotation-based properties
----------------------------------

The properties in this category are all :ref:`annotation_based:Annotation-based properties`, which means their getter
implementation will also perform a database query.
All of the listed properties therefore also take an additional ``cached`` argument in their initializer that allows
to mark individual properties as having a :ref:`standard_features:Cached getter`.
This can improve performance since the query will only be executed on the first getter access at the cost of
potentially not working with an up-to-date value.

``AnnotationProperty``
^^^^^^^^^^^^^^^^^^^^^^

The property class :class:`queryable_properties.properties.AnnotationProperty` represents the most simple common
annotation-based property.
It can be instanciated using any annotation and will use that annotation both in queries as well as to provide its
getter value.
This, however, means that the ``AnnotationProperty`` is only intended to be used with static/fixed annotations without
any dynamic components as its objects are set up by passing the annotation to the initializer.

As an example, the ``version_str`` property from the annotation :ref:`annotations:Implementation` section could be
reduced to (**not recommended**):

.. code-block:: python

    from django.db.models import Model, Value
    from django.db.models.functions import Concat
    from queryable_properties.properties import AnnotationProperty


    class ApplicationVersion(Model):
        ...  # other fields/properties

        version_str = AnnotationProperty(Concat('major', Value('.'), 'minor'))

.. note::
   This example is only supposed to demonstrate how to set up an ``AnnotationProperty``.
   Implementing a ``Concat`` annotation like this is not recommended as even the getter will perform a query, even
   though concatenating field values on the object level could simply be done without involving the database.

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``AnnotationProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.AnnotationProperty.__init__>`

   ``AnnotationProperty`` offers the following queryable property features:

   +------------+------------------------------------+
   | Feature    | Supported                          |
   +============+====================================+
   | Getter     | ✅ (all supported Django versions) |
   +------------+------------------------------------+
   | Setter     | ❌                                 |
   +------------+------------------------------------+
   | Filtering  | ✅ (all supported Django versions) |
   +------------+------------------------------------+
   | Annotation | ✅ (all supported Django versions) |
   +------------+------------------------------------+
   | Updating   | ❌                                 |
   +------------+------------------------------------+

``AggregateProperty``
^^^^^^^^^^^^^^^^^^^^^

*django-queryable-properties* also comes with a property class for simple aggregates that simply takes an aggregate
object and uses it for both queryset annotations as well as the getter.
This is therefore not entirely different from the ``AnnotationProperty`` class shown above.
The main difference between the two is that while ``AnnotationProperty`` uses ``QuerySet.annotate`` to query the getter
value, ``AggregateProperty`` uses ``QuerySet.aggregate``, which is slightly more efficient.
Using ``AggregateProperty`` for aggregate annotations might also make code more clear/readable.

As an example, the ``Application`` model could receive a simple property that returns the number of versions like the
one in the :ref:`annotation_based:Implementation` section of annotation-based properties.
:class:`queryable_properties.properties.AggregateProperty` allows to implement this in an even more condensed form:

.. code-block:: python

    from django.db.models import Count, Model
    from queryable_properties.properties import AggregateProperty


    class Application(Model):
        ...  # other fields/properties

        version_count = AggregateProperty(Count('versions'))

.. note::
   Since this property deals with aggregates, the notes
   :ref:`annotations:Regarding aggregate annotations across relations` apply when using such properties across
   relations in querysets.

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``AggregateProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.AggregateProperty.__init__>`

   ``AggregateProperty`` offers the following queryable property features:

   +------------+------------------------------------+
   | Feature    | Supported                          |
   +============+====================================+
   | Getter     | ✅ (all supported Django versions) |
   +------------+------------------------------------+
   | Setter     | ❌                                 |
   +------------+------------------------------------+
   | Filtering  | ✅ (all supported Django versions) |
   +------------+------------------------------------+
   | Annotation | ✅ (all supported Django versions) |
   +------------+------------------------------------+
   | Updating   | ❌                                 |
   +------------+------------------------------------+

``RelatedExistenceCheckProperty``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A common use case for properties is checking whether at least one related object exists.
For example, both the ``Application`` as well the ``Category`` models could define a property that checks whether any
corresponding applications versions exist in the database.

Without *django-queryable-properties*, the implementation could look similar to this:

.. code-block:: python

    from django.db import models


    class Category(models.Model):
        ...  # other fields/properties

        @property
        def has_versions(self):
            return self.applications.filter(versions__isnull=False).exists()


    class Application(models.Model):
        ...  # other fields/properties

        @property
        def has_versions(self):
            return self.versions.exists()

Instead of defining the properties like this, the property class
:class:`queryable_properties.properties.RelatedExistenceCheckProperty` could be used:

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import RelatedExistenceCheckProperty


    class Category(models.Model):
        ...  # other fields/properties

        has_versions = RelatedExistenceCheckProperty('applications__versions')


    class Application(models.Model):
        ...  # other fields/properties

        has_versions = RelatedExistenceCheckProperty('versions')

Instances of this property class take the query path to the related objects, which may also span multiple relations
using the ``__`` separator, as their first parameter.
Additionally, the optional ``negated`` parameter can be used to set up the property to check for the *non-existence*
of related objects instead.
In queries, the given query path is extended with the ``__isnull`` lookup, to determine whether related objects exist.
The path may also lead to a nullable field, which would allow to check for the existence of related objects that
have a value for a certain field.

.. note::
   Since the property's getter also performs a query for the existence check, the use of the
   ``RelatedExistenceCheckProperty`` is only recommended whenever a query would have to be performed anyway.
   It is therefore not recommended to be used to check if local non-relation fields are filled or even if a simple
   forward ``ForeignKey`` or ``OneToOneField`` has a value (which could be tested by checking the ``<fk_name>_id``
   attribute without performing a query).
   A :ref:`common/basic:\`\`ValueCheckProperty\`\`` may be better suited to check the value of local fields instead.

Not only does this property class allow to achieve the same functionality with less code, but it offers even more
functionality due to being a *queryable* property.
The class implements both queryset filtering as well as annotating (based on Django's ``Case``/``When`` objects), so
the properties can be used in querysets as well:

.. code-block:: python

    apps_with_versions = Application.objects.filter(has_versions=True)
    apps_without_versions = Application.objects.filter(has_versions=False)
    Category.objects.order_by('has_versions')

When being used in querysets like this, the filter condition is tested in a |in-subquery|_ (supported in all Django
versions supported by *django-queryable-properties*), which is built using the base manager (``_base_manager``) of the
property's associated model class.
This avoids ``JOIN`` ing the related models in the main queryset and therefore avoids duplicate objects in the results
whenever ...-to-many relations are involved.

.. |in-subquery| replace:: ``__in`` subquery
.. _in-subquery: https://docs.djangoproject.com/en/stable/ref/models/querysets/#in

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``RelatedExistenceCheckProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.RelatedExistenceCheckProperty.__init__>`

   ``RelatedExistenceCheckProperty`` offers the following queryable property features:

   +------------+------------------------------------+
   | Feature    | Supported                          |
   +============+====================================+
   | Getter     | ✅ (all supported Django versions) |
   +------------+------------------------------------+
   | Setter     | ❌                                 |
   +------------+------------------------------------+
   | Filtering  | ✅ (all supported Django versions) |
   +------------+------------------------------------+
   | Annotation | ✅ (**Django 1.8 or higher**)      |
   +------------+------------------------------------+
   | Updating   | ❌                                 |
   +------------+------------------------------------+

.. note::
   The query paths passed to ``RelatedExistenceCheckProperty`` may also refer to another queryable property as long as
   this property allows filtering with the ``isnull`` lookup.
