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

``model`` (required)
  Defines the model class the subquery returns instances of.
  Can be defined as any of the values accepted by the first argument of
  `foreign keys <https://docs.djangoproject.com/en/stable/ref/models/fields/#foreignkey>`_.
  In the example above, the model is defined as the string ``'ApplicationVersion'``.

``queryset`` (required)
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
  Specified properties must be annotatable.
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

Interacting with a ``SubqueryObjectProperty`` is designed to resemble interaction with foreign keys.
The property itself can be used to filter against instances or primary key values of the subquery model, while all
subquery model fields or properties can be accessed using ``__`` notation.
The following examples should be able to convey how a ``SubqueryObjectProperty`` can be used in filtering and ordering.

.. code-block:: python

    # The main property can be used to filter against subquery objects or primary keys
    some_version = ApplicationVersion.objects.get(...)
    Application.objects.filter(latest_version=some_version)
    Application.objects.filter(latest_version=42)
    Application.objects.filter(latest_version__isnull=True)  # Finds applications without latest versions

    # The 'pk' shortcut or the name of the subquery model's primary key field can also be used
    Application.objects.filter(latest_version__pk=42)
    Application.objects.filter(latest_version__id__gt=42)

    # Any of the subquery model's fields or properties handled by the SubqueryObjectProperty can also be used
    Application.objects.filter(latest_version__major__lt=3)
    Application.objects.filter(latest_version__version_str='1.2')

    # All of the field names shown above can also be used for ordering
    Application.objects.order_by('latest_version')  # Orders by primary key values of the latest versions
    Application.objects.order_by('-latest_version__pk')
    Application.objects.order_by('-latest_version__major')
    Application.objects.order_by('latest_version__version_str')

.. caution::
   If the subquery model contains foreign keys or its own ``SubqueryObjectProperty``, they are only represented by
   raw primary key values.
   Their sub-fields or sub-properties are not available for filtering and ordering.
   Hence, in the example above, it wouldn't be possible to filter or order by ``latest_version__application__name``.

Selection in querysets
^^^^^^^^^^^^^^^^^^^^^^

Just like any other annotatable queryable property, ``SubqueryObjectProperty``'s values can be selected in querysets
using the ``select_properties`` method.
However, since there are multiple parts to a ``SubqueryObjectProperty``, there are some additional options when
selecting.

Simply selecting the ``SubqueryObjectProperty`` itself will lead to a selection of all configured fields and queryable
properties of the subquery model:

.. code-block:: python

    for application in Application.objects.select_properties('latest_version')
        # None of the next lines will trigger an additional query as all fields are already populated
        print(application.latest_version)
        print(application.latest_version.pk)
        print(application.latest_version.major)
        print(application.latest_version.version_str)

It is also possible to only populate *some* of the configured fields and queryable properties.
All fields that haven't been selected are treated as deferred and accessing them will trigger a query.

.. code-block:: python

    for application in Application.objects.select_properties('latest_version__pk', 'latest_version__major'):
        # The next lines will not trigger a query since they have already been populated
        print(application.latest_version.pk)
        print(application.latest_version.major)
        # The next lines will trigger a query each since they haven't been populated
        print(application.latest_version.minor)
        print(application.latest_version.version_str)

.. caution::
   When selecting only a subset of the configured fields and queryable properties, make sure to always include the
   selection of the primary key value.
   If the primary key isn't populated, a ``SubqueryObjectProperty``'s getter will assume that no fields have been
   populated and perform a query to populate them all.
   This would render the initial selection of the otherfields useless.

In ``.values()`` or ``.values_list()`` queries, the property behaves like a foreign key again.
If it is requested via one of these methods, only the subquery object's primary key will be retrieved.
All other fields or queryable properties have to be requested individually.

.. code-block:: python

    for pk in Application.objects.select_properties('latest_version').values_list('latest_version', flat=True):
        print(pk)  # Will output the primary key value of the latest version

    for pk, major in Application.objects.select_properties('latest_version').values_list('latest_version__pk',
                                                                                         'latest_version__major'):
        print(pk)  # Will output the primary key value of the latest version
        print(major)  # Will output the value of the "major" field of the latest version

.. caution::
   Due to the behavior in ``.values()`` or ``.values_list()`` queries, prefetching values for a
   ``SubqueryObjectProperty`` via :func:`queryable_properties.utils.prefetch_queryable_properties` will also only
   prefetch the primary key value.
   Any of the configured fields and queryable propertie that should also be prefetched have to be stated explicitly
   via the ``__`` syntax shown above.
