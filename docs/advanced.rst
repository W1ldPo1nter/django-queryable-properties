Advanced features
=================

The :ref:`common:Common patterns` section of the documentation refers to property implementations that are essentially
simple and common wrappers around existing Django features internally, such as ``Case``/``When``, subqueries, etc.
The *django-queryable-properties* features described here are more advanced and go beyond the things that Django offers
on its own.

``SubqueryObjectProperty``: Getting an entire model object from a subquery
--------------------------------------------------------------------------

The property class :class:`queryable_properties.properties.SubqueryObjectProperty` allows to retrieve an entire model
object from a given subquery.
It can therefore be thought of as a ``ForeignKey`` that isn't based on an actual relation, but any custom subquery.
The ``SubqueryObjectProperty`` is designed to behave like a ``ForeignKey`` when interacting with it in various
scenarios.
Being based on ``Subquery`` objects, this property class can only be used in conjunction with a Django version that
supports custom subqueries, i.e. Django 1.11 or higher.

Let's look at a full example:

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import AnnotationProperty, SubqueryObjectProperty


    class Application(models.Model):
        """Represents a named application."""
        categories = models.ManyToManyField(Category, related_name='applications')
        name = models.CharField(max_length=255)

        latest_version = SubqueryObjectProperty(
            'ApplicationVersion',
            lambda: (ApplicationVersion.objects.filter(application=models.OuterRef('pk')).order_by('-major', '-minor')),
            property_names=('version_str',),
            cached=True,
        )


    class ApplicationVersion(models.Model):
        """Represents a version of an application using a major and minor version number."""
        application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='versions')
        major = models.PositiveIntegerField()
        minor = models.PositiveIntegerField()

        version_str = AnnotationProperty(Concat('major', Value('.'), 'minor'))

In this example, the ``Application`` model defines a ``SubqueryObjectProperty`` that will always load the latest
version object that exists for an application.
When accessing this property on an object, it will return the full ``ApplicationVersion`` object based on the first
row of the subquery or ``None`` if the subquery doesn't contain any rows:

.. code-block:: python

    application = Application.objects.get(...)
    # Since the property wasn't selected in the query above, the next line will execute a single query to fetch the
    # ApplicationVersion object (or None).
    if application.latest_version:
        print(application.latest_version.major)

In addition to the regular configuration options for :ref:`annotation_based:Annotation-based properties`, a
``SubqueryObjectProperty`` can be configured with the following parameters:

``model``
  Defines the model class the subquery returns instances of.
  Can be defined as any of the values accepted by the first argument of
  `foreign keys <https://docs.djangoproject.com/en/5.1/ref/models/fields/#foreignkey>`_.
  In the example above, the model is defined as the string ``'ApplicationVersion'``.

``queryset``
  The actual queryset to retrieve subquery objects from.
  Follows the same rules as the queryset parameter of any other
  :ref:`common:Subquery-based properties (Django 1.11 or higher)`.

``field_names`` (optional)
  A sequence of field names that should be populated on subquery objects.
  If this option is not used (like in the example above), all concrete fields of the model will be queried and
  populated.
  If a restricted set of fields is given, all other fields will be treated as deferred when constructing instances
  (the same behavior as ``.only()``/``.defer()`` calls).
  The primary key field of the model will always be included automatically and does not have to be specified here.

``property_names`` (optional)
  If the subquery model defines its own queryable properties, a ``SubqueryObjectProperty`` can be configured to also
  populate their values when retrieving subquery objects.
  This option can be used to configure a sequence containing the property names to populate.
  If it is not used, no queryable properties will be populated on submodel instances.

How it works
^^^^^^^^^^^^

Since Django can generally only retrieve one value per field or annotation, a ``SubqueryObjectProperty`` has to do some
extra work to be able to retrieve entire model instances.
In fact, defining a ``SubqueryObjectProperty`` will actually define multiple queryable properties at once in most cases.
To properly work with Django's annotation system, a :class:`queryable_properties.properties.SubqueryFieldProperty` will
be created for each field or queryable property that should be handled for subquery objects.
The actual ``SubqueryObjectProperty`` will handle the primary key value of the subquery object internally while
managing all created sub-properties.

These additional properties are automatically named
``<name of the object property>-<name of the represented field or property>``.
However, these internal property names should not be relevant unless such properties are to be populated in raw queries,
where these field names have to be used.
This means that in the example above, the ``Application`` model doesn't just contain a single queryable property - there
are actually five properties:

* ``latest_version``: The actual ``SubqueryObjectProperty`` that handles the primary key value internally
* ``latest_version-application``: Handles the ``application`` field of subquery objects
* ``latest_version-major``: Handles the ``major`` field of subquery objects
* ``latest_version-minor``: Handles the ``minor`` field of subquery objects
* ``latest_version-version_str``: Handles the ``version_str`` property of subquery objects

As a consequence, the generated SQL of queries selecting ``SubqueryObjectProperty`` can become quite large since they
essentially select multiple ``SubqueryFieldProperty`` instances that internally use the same queryset but select a
different field or queryable property each.
Therefore, the SQL will contain multiple sub-``SELECT`` clauses that are almost identical.
However, this should **not** affect the actual database performance as any DBMS will figure out that all these queries
refer to the same object and then optimize internally.

Filtering/Ordering in querysets
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

TODO

Selection in querysets
^^^^^^^^^^^^^^^^^^^^^^

TODO
