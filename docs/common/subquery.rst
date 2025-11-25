Subquery-based properties
-------------------------

The properties in this category are all based on custom subqueries, i.e. they utilize Django's ``Subquery`` objects.
They are therefore :ref:`annotation_based:Annotation-based properties`, which means their getter implementation will
also perform a database query.
Due to the utilization of ``Subquery`` objects, these properties can only be used in conjunction with a Django version
that supports custom subqueries, i.e. Django 1.11 or higher.

Arguments providing subqueries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

All subquery-based properties take a queryset that will be used to generate the custom subquery as one of their
arguments.
This queryset is always expected to be a regular queryset, i.e. **not** a ``Subquery`` object - the properties will
build these objects on their own using the given queryset.
The specified queryset can (and in most cases should) contain ``OuterRef`` objects to filter the subquery's rows based
on the outer query.
These ``OuterRef`` objects will always be based on the model the property is defined on - all fields of that model or
related fields starting from that model can therefore be referenced.

Instead of specifying a queryset directly, the subquery-based properties can also take a callable as their ``queryset``
parameter, which in turn must return the queryset.
This callable may either take a single argument, which receives the model class of the outer queryset that embeds the
subquery (useful in inheritance scenarios) or take no arguments.
Providing a callable may help in cases where the model class for the subquery's queryset cannot be imported on the
module level or is defined later in the same module.

``SubqueryFieldProperty``
^^^^^^^^^^^^^^^^^^^^^^^^^

The property class :class:`queryable_properties.properties.SubqueryFieldProperty` allows to retrieve the value of any
field from a specified subquery.
The field does not have to be a static model field, but may also be an annotated field (which can even be used to work
around the problem described in :ref:`annotations:Regarding aggregate annotations across relations`) or even a
queryable property as long as it was selected as described in :ref:`annotations:Selecting annotations`.

Based on the ``version_str`` property for the ``ApplicationVersion`` shown in the :ref:`annotations:Implementation`
documentation for annotatable properties, an example property could be implemented for the ``Application`` model that
determines the highest version for each application via a subquery:

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import SubqueryFieldProperty


    class Application(models.Model):
        ...  # other fields/properties

        highest_version = SubqueryFieldProperty(
            (ApplicationVersion.objects.select_properties('version_str')
                                       .filter(application=models.OuterRef('pk'))
                                       .order_by('-major', '-minor')),
            field_name='version_str',  # The field to extract the property value from
            output_field=models.CharField()  # Only required in cases where Django can't determine the type on its own
        )

.. note::
   Since the property can only return a single value per object, the subquery is limited to the first row (the
   specified queryset and field name is essentially transformed into ``Subquery(queryset.values(field_name)[:1])``).
   If a subquery returns multiple rows, it should therefore be ordered in a way that puts the desired value into the
   first row.

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``SubqueryFieldProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.SubqueryFieldProperty.__init__>`

   ``SubqueryFieldProperty`` offers the following queryable property features:

   +------------+------------------------------------+
   | Feature    | Supported                          |
   +============+====================================+
   | Getter     | ✅ (**Django 1.11 or higher**)     |
   +------------+------------------------------------+
   | Setter     | ❌                                 |
   +------------+------------------------------------+
   | Filtering  | ✅ (**Django 1.11 or higher**)     |
   +------------+------------------------------------+
   | Annotation | ✅ (**Django 1.11 or higher**)     |
   +------------+------------------------------------+
   | Updating   | ❌                                 |
   +------------+------------------------------------+

``SubqueryExistenceCheckProperty``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The property class :class:`queryable_properties.properties.SubqueryExistenceCheckProperty` is similar to
:ref:`common/annotation_based:\`\`RelatedExistenceCheckProperty\`\``, but can be used to perform any kind of existence
check via a subquery.
The objects whose existence is to be determined does therefore not have to be related to the class the property is
defined on via a ``ForeignKey`` or another relation field.

To perform this check, the given queryset is wrapped into an ``Exists`` object, which may also be negated using the
property's ``negated`` argument.

For an example use case, certain applications may be so popular that they receive their own category with the same
name as the application.
To determine whether an application has its own category, a ``SubqueryExistenceCheckProperty`` could be used:

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import SubqueryExistenceCheckProperty


    class Application(models.Model):
        ...  # other fields/properties

        has_own_category = SubqueryExistenceCheckProperty(Category.objects.filter(name=models.OuterRef('name')))

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``SubqueryExistenceCheckProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.SubqueryExistenceCheckProperty.__init__>`

   ``SubqueryExistenceCheckProperty`` offers the following queryable property features:

   +------------+------------------------------------+
   | Feature    | Supported                          |
   +============+====================================+
   | Getter     | ✅ (**Django 1.11 or higher**)     |
   +------------+------------------------------------+
   | Setter     | ❌                                 |
   +------------+------------------------------------+
   | Filtering  | ✅ (**Django 1.11 or higher**)     |
   +------------+------------------------------------+
   | Annotation | ✅ (**Django 1.11 or higher**)     |
   +------------+------------------------------------+
   | Updating   | ❌                                 |
   +------------+------------------------------------+

``SubqueryObjectProperty``
^^^^^^^^^^^^^^^^^^^^^^^^^^

The property class :class:`queryable_properties.properties.SubqueryObjectProperty` allows to retrieve an entire model
object from a given subquery.
It can therefore be thought of as a ``ForeignKey`` that isn't based on an actual relation, but any custom subquery.
The ``SubqueryObjectProperty`` is designed to behave like a ``ForeignKey`` when interacting with it in various
scenarios.

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

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``SubqueryObjectProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.SubqueryObjectProperty.__init__>`

   ``SubqueryObjectProperty`` offers the following queryable property features:

   +------------+------------------------------------+
   | Feature    | Supported                          |
   +============+====================================+
   | Getter     | ✅ (**Django 1.11 or higher**)     |
   +------------+------------------------------------+
   | Setter     | ❌                                 |
   +------------+------------------------------------+
   | Filtering  | ✅ (**Django 1.11 or higher**)     |
   +------------+------------------------------------+
   | Annotation | ✅ (**Django 1.11 or higher**)     |
   +------------+------------------------------------+
   | Updating   | ❌                                 |
   +------------+------------------------------------+

How it works
""""""""""""

Since Django can generally only retrieve one value per field or annotation, a ``SubqueryObjectProperty`` has to do some
extra work to be able to retrieve entire model instances.
In fact, defining a ``SubqueryObjectProperty`` will actually define multiple queryable properties at once in most cases.
To properly work with Django's annotation system, a :ref:`common/subquery:\`\`SubqueryFieldProperty\`\`` will be
created for each field or queryable property that should be handled for subquery objects.
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
"""""""""""""""""""""""""""""""

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
""""""""""""""""""""""

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
   This would render the initial selection of the other fields useless.

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
