Properties dealing with model inheritance
-----------------------------------------

The properties in this category are designed to help with model inheritance scenarios, specifically
`Multi-table inheritance <https://docs.djangoproject.com/en/stable/topics/db/models/#multi-table-inheritance>`_.
When working with this kind of inheritance, a base model is often used to build generic business logic for multiple
child models or to allow relations to them.
When querying objects this base model, it is often difficult to know which final model each object belongs to.
This is where the properties of this category come in: to help make distinctions based on the actual model of each
object in efficient way.

Examples
^^^^^^^^

Example code for properties dealing with model inheritance is based on different example models than the rest of the
documentation since an inheritance structure is required to properly demonstrate such properties.
The following code snippet shows the example models for inheritance-based properties - which were taken from Django's
documentation itself and extended with the ``Event`` model and some instances:

.. code-block:: python

    from django.db import models


    class Place(models.Model):
        name = models.CharField(max_length=50)
        address = models.CharField(max_length=80)

        def __str__(self):
            return self.name


    class Restaurant(Place):
        serves_hot_dogs = models.BooleanField(default=False)
        serves_pizza = models.BooleanField(default=False)


    class Event(models.Model):
        place = models.ForeignKey(Place, on_delete=models.CASCADE)
        date = models.DateTimeField()


    p = Place.objects.create(name='Empire State Building', address='New York')
    r = Restaurant.objects.create(name='Stoned Pizza', address='New York', serves_pizza=True)

These example models allow to define different kinds of places while being able to create events for any of them.

``InheritanceModelProperty``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Working with multi-table inheritance can often be made more convenient by being able to determine or display
information about the final model class of an object - and this is what the ``InheritanceModelProperty`` provides.
Properties of this kind are :ref:`annotation_based:Annotation-based properties` (i.e. the getter also performs a query
if the value isn't already cached) and their value determination is achieved using ``CASE``/``WHEN`` expressions based
on Django's ``Case``/``When`` objects, which means that this property class can only be properly used in Django
versions that provide these features (1.8+).

Looking at the example models above, one may want to build an admin integration for the ``Event`` model and show the
``place`` field there by adding it to the admin's ``list_display`` and quickly realize that this field only shows the
string representation for each associated place.
However, there's no built-in way to display what kind of place is linked to each event - it could be a basic place or
a restaurant each time.
This is where an ``InheritanceModelProperty`` may help as it can simply be used to determine the verbose name of the
final model (among various other use cases), which could be achieved by adding the property to the ``Place`` model:

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import InheritanceModelProperty


    class Place(models.Model):
        ...

        type_label = InheritanceModelProperty(lambda cls: str(cls._meta.verbose_name), models.CharField())

Using the :ref:`admin:Admin integration`, the ``list_display`` for the admin may now contain ``'place'`` as well as
``'place__type_label'`` to show both the name and the type of each associated place.

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``InheritanceModelProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.InheritanceModelProperty.__init__>`

   ``InheritanceModelProperty`` offers the following queryable property features:

   +------------+------------------------------------+
   | Feature    | Supported                          |
   +============+====================================+
   | Getter     | ✅ (**Django 1.8 or higher**)      |
   +------------+------------------------------------+
   | Setter     | ❌                                 |
   +------------+------------------------------------+
   | Filtering  | ✅ (**Django 1.8 or higher**)      |
   +------------+------------------------------------+
   | Annotation | ✅ (**Django 1.8 or higher**)      |
   +------------+------------------------------------+
   | Updating   | ❌                                 |
   +------------+------------------------------------+

``InheritanceObjectProperty``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When working with model inheritance, a common problem is figuring out the final model class of instances efficiently.
The property class :class:`queryable_properties.properties.InheritanceObjectProperty` attempts to solve this problem
by determining the final model class and returning the model instance as an instance of that class.
Being based on ``Case``/``When`` objects, this property class can only be used in conjunction with a Django version
that supports these expressions, i.e. Django 1.8 or higher.

Let's look at an example based on the example models above:

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import InheritanceObjectProperty


    class Place(models.Model):
        ...

        subclass_instance = InheritanceObjectProperty(cached=True)


    class Restaurant(Place):
        ...


    for place in Place.objects.select_properties('subclass_instance').order_by('pk'):
        print(repr(place))
        print(repr(place.subclass_instance))

    # Output:
    # <Place: Empire State Building>
    # <Place: Empire State Building>
    # <Place: Stoned Pizza>
    # <Restaurant: Stoned Pizza>

The base example defines a place and a restaurant (which is also a place due to inheritance) object and here the
``Place`` model is used to query all available places.
While all objects returned via the query are base ``Place`` instances, the ``InheritanceObjectProperty`` allows to
access the instance of the final class for each instance (with all subclass fields properly populated).
Due to the use of ``select_properties``, the property will already be populated for each instance, so the entire loop
only executes a single query.

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``InheritanceObjectProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.InheritanceObjectProperty.__init__>`

   ``InheritanceObjectProperty`` offers the following queryable property features:

   +------------+------------------------------------+
   | Feature    | Supported                          |
   +============+====================================+
   | Getter     | ✅ (**Django 1.8 or higher**)      |
   +------------+------------------------------------+
   | Setter     | ❌                                 |
   +------------+------------------------------------+
   | Filtering  | ✅ (**Django 1.8 or higher**)      |
   +------------+------------------------------------+
   | Annotation | ✅ (**Django 1.8 or higher**)      |
   +------------+------------------------------------+
   | Updating   | ❌                                 |
   +------------+------------------------------------+

How it works
""""""""""""

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
""""""""""""""""""

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

``ContentTypeProperty``
^^^^^^^^^^^^^^^^^^^^^^^

The property class :class:`queryable_properties.properties.ContentTypeProperty` allows to determine the content type
of the objects it's attached to.
This includes handling model inheritance correctly and therefore reporting the actual content type of each object, even
if it was queried using a base model.
Due to its interaction with the ``ContentType`` model, it requires Django's
`contenttypes framework <https://docs.djangoproject.com/en/stable/ref/contrib/contenttypes/>`_  to be installed.
Due to the features it uses to construct its queries, this property class requires Django 4.0 or higher.

Let's look at an example based on the example models above:

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import ContentTypeProperty


    class Place(models.Model):
        ...

        content_type = ContentTypeProperty(cached=True)


    class Restaurant(Place):
        ...


    for place in Place.objects.select_properties('content_type').order_by('pk'):
        print(repr(place))
        print(repr(place.content_type))

    # Output:
    # <Place: Empire State Building>
    # <ContentType: places | place>
    # <Place: Stoned Pizza>
    # <ContentType: places | restaurant>

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``ContentTypeProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.ContentTypeProperty.__init__>`

   ``ContentTypeProperty`` offers the following queryable property features:

   +------------+------------------------------------+
   | Feature    | Supported                          |
   +============+====================================+
   | Getter     | ✅ (**Django 4.0 or higher**)      |
   +------------+------------------------------------+
   | Setter     | ❌                                 |
   +------------+------------------------------------+
   | Filtering  | ✅ (**Django 4.0 or higher**)      |
   +------------+------------------------------------+
   | Annotation | ✅ (**Django 4.0 or higher**)      |
   +------------+------------------------------------+
   | Updating   | ❌                                 |
   +------------+------------------------------------+
