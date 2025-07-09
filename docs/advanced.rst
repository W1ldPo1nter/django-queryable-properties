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
  All primary key fields of the model will always be included automatically and do not have to be specified here.

``property_names`` (optional)
  If the subquery model defines its own queryable properties, a ``SubqueryObjectProperty`` can be configured to also
  populate their values when retrieving subquery objects.
  This option can be used to configure a sequence containing the property names to populate.
  Specified properties must be annotatable.
  If it is not used, no queryable properties will be populated on submodel instances.

``SubqueryObjectProperty``: How it works
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Since Django can generally only retrieve one value per field or annotation, a ``SubqueryObjectProperty`` has to do some
extra work to be able to retrieve entire model instances.
In fact, defining a ``SubqueryObjectProperty`` will actually define multiple queryable properties at once in most cases.
To properly work with Django's annotation system, a :class:`queryable_properties.properties.SubqueryFieldProperty` will
be created for each field or queryable property that should be handled for subquery objects.
The actual ``SubqueryObjectProperty`` will handle the primary key value (or the value of the first primary key field
in composite primary key scenarios) of the subquery object internally while managing all created sub-properties.

These additional properties are automatically named
``<name of the object property>-<name of the represented field or property>``.
However, these internal property names should not be relevant unless such properties are to be populated in raw queries,
where these field names have to be used.
This means that in the example above, the ``Application`` model doesn't just contain a single queryable property - there
are actually five properties:

* ``latest_version``: The actual ``SubqueryObjectProperty`` that handles the primary key value internally
* ``latest_version-application_id``: Handles the ``application`` field (whose column name is ``application_id``) of
  subquery objects
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

    # The 'pk' shortcut (non-composite PKs only) or the name of the subquery model's primary key field can also be used
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

.. note::
   The ``pk`` shortcut is not available if the subquery model uses a composite primary key as the primary key value
   cannot be represented by a single column.
   However, it is still possible to filter the main property by a composite primary key as a tuple or to filter the
   individual primary key fields using ``__`` notation.

.. note::
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

.. note::
   The ``pk`` shortcut is not available if the subquery model uses a composite primary key as the primary key value
   cannot be represented by a single column.
   However, it is still possible to select all primary key fields via their name using ``__`` notation.

.. caution::
   When selecting only a subset of the configured fields and queryable properties, make sure to always include the
   selection of all primary key values.
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
   The ``pk`` shortcut is not available if the subquery model uses a composite primary key as the primary key value
   cannot be represented by a single column.
   Also, the selection of the main property will only select the first primary key field.
   Select the individual primary key fields using ``__`` notation to get all parts of the primary key.

``InheritanceObjectProperty``: Getting the final subclass object in inheritance scenarios
-----------------------------------------------------------------------------------------

When working with model inheritance, a common problem is figuring out the final model class of instances efficiently.
The property class :class:`queryable_properties.properties.InheritanceObjectProperty` attempts to solve this problem
by determining the final model class and returning the model instance as an instance of that class.
Being based on ``Case``/``When`` objects, this property class can only be used in conjunction with a Django version
that supports these expressions, i.e. Django 1.8 or higher.

Let's look at a full example based on the example inheritance models from Django's documentation:

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import InheritanceObjectProperty


    class Place(models.Model):
        name = models.CharField(max_length=50)
        address = models.CharField(max_length=80)

        subclass_instance = InheritanceObjectProperty(cached=True)

        def __str__(self):
            return self.name


    class Restaurant(Place):
        serves_hot_dogs = models.BooleanField(default=False)
        serves_pizza = models.BooleanField(default=False)


    p = Place.objects.create(name='Empire State Building', address='New York')
    r = Restaurant.objects.create(name='Stoned Pizza', address='New York', serves_pizza=True)

    for place in Place.objects.select_properties('subclass_instance').order_by('pk'):
        print(repr(place))
        print(repr(place.subclass_instance))

    # Output:
    # <Place: Empire State Building>
    # <Place: Empire State Building>
    # <Place: Stoned Pizza>
    # <Restaurant: Stoned Pizza>

In this example, a place and a restaurant (which is also a place due to inheritance) object are created and the
``Place`` model is used to query all available places.
While all objects returned via the query are base ``Place`` instances, the ``InheritanceObjectProperty`` allows to
access the instance of the final class for each instance (with all subclass fields properly populated).
Due to the use of ``select_properties``, the property will already be populated for each instance, so the entire loop
only executes a single query.

The ``InheritanceObjectProperty`` property class is based on
:ref:`common:\`\`InheritanceModelProperty\`\`: Getting information about the final model class` and therefore supports
its ``depth`` argument in addition to all common property arguments.

``InheritanceObjectProperty``: How it works
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As mentioned above, ``InheritanceObjectProperty`` is based on ``InheritanceModelProperty`` and therefore contains
information about the final model class of each instance on the queryset level.
Specifically, ``InheritanceObjectProperty`` instances use strings in the form of ``"<app_label>.<ModelName>"`` as
their values in queries.
If the models shown above would live in an app called ``places``, possible values would therefore be ``"places.Place"``
and ``"places.Restaurant"``.
On the object level, this value is then used to determine the final model class via Django's app registry.

Additionally, ``InheritanceObjectProperty`` instances automatically perform some ``.select_related()`` setup while
querying.
This allows to query all possbible submodel fields in the same queryset, thus executing only a single query.
The model that was determined for each instance is then used to figure out which of the child relations to follow to
get the instance of the final model class.

.. note::
   The ``.select_related()`` operation is performed lazily just before the query is executed (and only if no queryset
   features which would conflict with it are used).
   This is done to ensure that the required selection of the child objects is not accidentally reverted through other
   queryset modifications.
   As a consequence, the queryset and its query will not reflect the selection of the child instances when inspecting
   them (or their SQL code) before the query is actually executed.

Usage in querysets
^^^^^^^^^^^^^^^^^^

When an ``InheritanceObjectProperty`` is used in queryset operations other than selection via ``select_properties``,
it behaves differently compared to the object level.
As already described in the previous section, an ``InheritanceObjectProperty`` is represented by strings in the form
of ``"<app_label>.<ModelName>"`` in queries, which means that any interaction with such properties in queryset means
interacting with these string values.
For example, using ``.order_by()`` or ``.values()`` with ``InheritanceObjectProperty`` instances means ordering by or
retrieving these strings.
The same applies to filtering, although there are some convenience additions to be able to filter directly by model
classes or objects.
Refer to the following examples, which are based on the example models and objects above, to get an idea of how to work
with these properties in queryset operations:

.. code-block:: python

    # Filtering can be performed using strings or model classes
    # The following queries will find object p, but not object r
    Place.objects.filter(subclass_instance='places.Place')
    Place.objects.filter(subclass_instance=Place)

    # Filtering can also take model instances, which leads to both type and primary key being compared
    # The following query will find no objects since p is a base Place and thus does not match the condition
    # "model class is Restaurant and pk is p's pk"
    Place.objects.filter(subclass_instance=Restaurant(pk=p.pk))

    # The following query will place all base Place objects before Restaurant objects
    # since 'places.Place' < 'places.Restaurant'
    Place.objects.order_by('subclass_instance')

    # Using .values/.values_list returns the string values
    for data in Place.objects.select_properties('subclass_instance').order_by('pk').values('name', 'subclass_instance'):
        print(data)
    # Output:
    # {'name': 'Empire State Building', 'subclass_instance': 'places.Place'}
    # {'name': 'Stoned Pizza', 'subclass_instance': 'places.Restaurant'}
