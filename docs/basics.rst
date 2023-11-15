Basics
======

Implementing queryable properties
---------------------------------

There are two ways to implement a queryable property:

- Using decorated methods directly on the model class (just like regular properties)
- Implementing the queryable property as a class and using its instances as class attributes on the model class (much
  like model fields)

Say we'd want to implement a queryable property for the ``ApplicationVersion`` example model that simply returns the
combined version information as a string.
The two following sections show how to implement such a queryable property - for the sake of simplicity, the examples
only show how to implement a getter and setter (which could also be implemented using a regular property).
The following chapters of this documentation will show all available decorators, mixins and implementable methods in
detail.

Decorator-based approach
^^^^^^^^^^^^^^^^^^^^^^^^

The decorator-based approach uses the class :class:`queryable_properties.properties.queryable_property` and its methods
as decorators:

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import queryable_property


    class ApplicationVersion(models.Model):
        ...

        @queryable_property
        def version_str(self):
            return '{major}.{minor}'.format(major=self.major, minor=self.minor)

        @version_str.setter
        def version_str(self, value):
            # Don't implement any validation to keep the example simple.
            self.major, self.minor = value.split('.')

Using the decorator methods without actually decorating
"""""""""""""""""""""""""""""""""""""""""""""""""""""""

Python's regular properties also allow to define properties without using ``property`` as a decorator.
To do this, the individual methods that should make up the property can be passed to the ``property`` constructor:

.. code-block:: python

    class MyClass(object):

        def get_x(self):
            return self._x

        def set_x(self, value):
            self._x = value

        x = property(get_x, set_x)

Queryable properties do **not** allow to do this in the same way because of two reasons:

- To encourage implementing properties using decorators, which is cleaner and makes code more readable.
- Since queryable properties have a lot more functionality and options than regular properties, they would need to
  support a huge number of constructor parameters, which would make the constructor too complex and harder to maintain.

However, there are use cases where an option similar to the non-decorator usage of regular properties would be nice to
have, e.g. when implementing a property without a getter or when the individual getter/setter methods are already
present and cannot be easily deprecated in favor of the property.
This is why queryable properties do support this form of defining a property - but in a slightly different way: the
decorator methods can simply be chained together (this also works for all decorators introduced in later chapters).

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import queryable_property


    class ApplicationVersion(models.Model):
        ...

        def get_version_str(self):
            return '{major}.{minor}'.format(major=self.major, minor=self.minor)

        def set_version_str(self, value):
            # Don't implement any validation to keep the example simple.
            self.major, self.minor = value.split('.')

        version_str = queryable_property(get_version_str).setter(set_version_str)

By not passing a getter function to the ``queryable_property`` constructor, a queryable property without a getter can
be defined (``queryable_property().setter(set_version_str)`` for the example above).
This can even be used to make a getter-less queryable property while still decorating the setter (or mixing and
matching chaining and decorating in general):

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import queryable_property


    class ApplicationVersion(models.Model):
        ...

        version_str = queryable_property()  # Property without a getter

        @version_str.setter
        def version_str(self, value):
            # Don't implement any validation to keep the example simple.
            self.major, self.minor = value.split('.')

Class-based approach
^^^^^^^^^^^^^^^^^^^^

Using the class-based approach, the queryable property is implemented as a subclass of
:class:`queryable_properties.properties.QueryableProperty`:

.. code-block:: python

    from django.db import models
    from queryable_properties.properties import QueryableProperty, SetterMixin


    class VersionStringProperty(SetterMixin, QueryableProperty):

        def get_value(self, obj):
            return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)

        def set_value(self, obj, value):
            # Don't implement any validation to keep the example simple.
            obj.major, obj.minor = value.split('.')


    class ApplicationVersion(models.Model):
        ...

        version_str = VersionStringProperty()

Common property arguments
^^^^^^^^^^^^^^^^^^^^^^^^^

Queryable properties that are created using either approach take additional, common keyword arguments that can be used
to configure property instances further.
These are:

``verbose_name``
  A human-readable name for the property instance, similar to the verbose name of an instance of one of Django's model
  fields.
  Used for UI representations of queryable properties.
  If no verbose name is set up for a property, one will be generated based on the property's name.

For both the class-based and the decorator-based approach, these keyword arguments can be set via their respective
constructor.
For the example property above, this could look like the following example:

.. code-block:: python

    from django.utils.translation import gettext_lazy as _


    class ApplicationVersion(models.Model):
        ...

        # Class-based
        version_str = VersionStringProperty(verbose_name=_('Full Version Number'))

        # Decorator-based
        @queryable_property(verbose_name=_('Full Version Number'))
        def version_str(self):
            ...


When to use which approach
^^^^^^^^^^^^^^^^^^^^^^^^^^

It all depends on your needs and preferences, but a general rule of thumb is using the class-based approach to
implement re-usable queryable properties or to be able to use inheritance.
It would also be pretty easy to write parameterizable property classes by adding parameters to their ``__init__``
methods.

Class-based implementations come, however, with the small disadvantage of having to define the property's logic outside
of the actual model class (unlike regular property implementations).
It would therefore probably be preferable to use the decorator-based approach for unique, non-reusable implementations.

Enabling queryset operations
----------------------------

To actually interact with queryable properties in queryset operations, the queryset extensions provided by
*django-queryable-properties* must be used since regular querysets cannot deal with queryable properties on their own.

The following sections describe how to properly set this up to either use the extensions by either applying them to
querysets of models in general via managers or by creating querysets with the queryable properties extensions on
demand.

Defining managers on models
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The most common way to use the queryset extensions is by defining a manager that produces querysets with queryable
properties functionality.
The easiest way to do this is by simply using the :class:`queryable_properties.managers.QueryablePropertiesManager`:

.. code-block:: python

    from queryable_properties.managers import QueryablePropertiesManager


    class ApplicationVersion(models.Model):
        ...

        objects = QueryablePropertiesManager()

This manager allows to use the queryable properties in querysets created by this manager (e.g. via
``ApplicationVersion.objects.all()``).

For scenarios where querysets or managers need other extensions or base classes, *django-queryable-properties* also
offers a queryset class as well as mixins for managers or querysets that can be combined with other base classes:

* Queryset class: :class:`queryable_properties.managers.QueryablePropertiesQuerySet`
* Queryset mixin: :class:`queryable_properties.managers.QueryablePropertiesQuerySetMixin`
* Manager mixin: :class:`queryable_properties.managers.QueryablePropertiesManagerMixin`

When implementing custom queryset classes, a manager class can be generated from the queryset class using
``CustomQuerySet.as_manager()`` or ``CustomManager.from_queryset(CustomQuerySet)``.

.. warning::
   Since queryable property interaction in querysets is tied to the specific extensions, those extensions are also
   required when trying to access queryable properties on related models.
   This means that using the manager approach, all models from which queries that interact with queryable properties
   are performed need to use a manager as described above, even if a model doesn't implement its own queryable
   properties.

   For example, if queryset filtering was implemented for the ``version_str`` property shown above, it could also be
   used in querysets of the ``Application`` model like this:

   .. code-block:: python

       Application.objects.filter(versions__version_str='1.2')

   To make this work, the ``objects`` manager of the ``Application`` model must also be a
   ``QueryablePropertiesManager``, even if the model does not define queryable properties of its own.

   If using a special manager just to access queryable properties on related models is not desirable, then the
   following approaches to apply the queryable properties extensions on demand should offer an alternative.

Creating managers/querysets on demand
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The non-mixin classes provided by *django-queryable-properties* also allow to create managers or querysets on demand,
regardless of the presence of a manager with queryable properties extensions on the corresponding model.
Both the :class:`queryable_properties.managers.QueryablePropertiesManager` and the
:class:`queryable_properties.managers.QueryablePropertiesQuerySet` offer a ``get_for_model`` method for this purpose:

.. code-block:: python

    from queryable_properties.managers import QueryablePropertiesManager, QueryablePropertiesQuerySet

    # Create an ad hoc manager that produces querysets with queryable property extensions for the given model.
    ad_hoc_manager = QueryablePropertiesManager.get_for_model(MyModel)
    # Create an ad hoc queryset with queryable property extensions for the given model.
    ad_hoc_queryset = QueryablePropertiesQuerySet.get_for_model(MyModel)

.. note::
   Querysets created using ``QueryablePropertiesQuerySet.get_for_model`` use the model's default manager to create the
   underlying queryset, i.e. the queryset is generated using ``model._default_manager.all()`` before the queryable
   properties extensions are applied.

Applying the extensions to existing managers/querysets on demand
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There might be scenarios where interacting with queryable properties is desired in an existing queryset or manager.
The mixin classes provided by *django-queryable-properties* allow to inject the queryable properties extensions into
an existing queryset or manager using their ``apply_to`` method.
Both the :class:`queryable_properties.managers.QueryablePropertiesManagerMixin` and the
:class:`queryable_properties.managers.QueryablePropertiesQuerySetMixin` create a copy of the original object in the
process, leaving said object untouched.

.. code-block:: python

    from queryable_properties.managers import QueryablePropertiesManagerMixin, QueryablePropertiesQuerySetMixin

    # Create an ad hoc manager based off the given manager instance that produces querysets with queryable property
    # extensions for the given model.
    ad_hoc_manager = QueryablePropertiesManagerMixin.apply_to(some_manager)
    # Create an ad hoc queryset with queryable property extensions for the given model.
    some_queryset = MyModel.objects.filter(...).order_by(...)  # A queryset without queryable properties features.
    ad_hoc_queryset = QueryablePropertiesQuerySetMixin.apply_to(some_queryset)
    ad_hoc_queryset.select_properties(...)  # Now queryable properties features can be used.
