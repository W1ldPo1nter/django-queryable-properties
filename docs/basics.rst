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

By not passing anything to the ``queryable_property`` constructor, a queryable property without a getter can be defined
(``queryable_property().setter(set_version_str)`` for the example above).
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

When to use which approach
^^^^^^^^^^^^^^^^^^^^^^^^^^

It all depends on your needs and preferences, but a general rule of thumb is using the class-based approach to 
implement re-usable queryable properties or to be able to use inheritance.
It would also be pretty easy to write parameterizable property classes by adding parameters to their ``__init__``
methods.

Class-based implementations come, however, with the small disadvantage of having to define the property's logic outside
of the actual model class (unlike regular property implementations).
It would therefore probably be preferable to use the decorator-based approach for unique, non-reusable implementations.

Using the required manager/queryset
-----------------------------------

If we were to actually implement queryset-related logic in the examples above, the ``ApplicationVersion`` model would
be missing one small detail to actually be able to use the queryable properties in querysets: the model must use a
special queryset class, which can most easily be achieved by using a special manager:

.. code-block:: python

    from queryable_properties.managers import QueryablePropertiesManager


    class ApplicationVersion(models.Model):
        ...

        objects = QueryablePropertiesManager()

This manager allows to use the queryable properties in querysets created by this manager (e.g. via
``ApplicationVersion.objects.all()``).
If there's a need to use another special queryset class, ``queryable_properties`` also comes with a mixin to add its
logic to other custom querysets: ``queryable_properties.managers.QueryablePropertiesQuerySetMixin``.
A manager class can then be generated from the queryset class using ``CustomQuerySet.as_manager()`` or
``CustomManager.from_queryset(CustomQuerySet)``.

Using the special manager/queryset class may not only be important for models that define queryable properties.
Since most features of queryable properties can also be used on related models in queryset operations, the manager is
required whenever queryable property functionality should be offered, even if the corresponding model doesn't implement
its own queryable properties.
For example, if queryset filtering was implemented for the ``version_str`` property shown above, it could also be used
in querysets of the ``Application`` model like this:

.. code-block:: python

    Application.objects.filter(versions__version_str='1.2')

To make this work, the ``objects`` manager of the ``Application`` model must also be a ``QueryablePropertiesManager``,
even if the model does not define queryable properties of its own.
