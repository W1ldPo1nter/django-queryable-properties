Standard property features
==========================

Queryable properties offer almost all the features of regular properties while adding some additional options.

Getter
------

Queryable properties define their getter method the same way as regular properties do when using the decorator-based
approach:

.. code-block:: python

    from queryable_properties.properties import queryable_property


    class ApplicationVersion(models.Model):
        ...

        @queryable_property
        def version_str(self):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=self.major, minor=self.minor)

Using the class-based approach, the queryable property's method ``get_value`` must be implemented instead, taking the
model object to retrieve the value from as its only parameter:

.. code-block:: python

    from queryable_properties.properties import QueryableProperty


    class VersionStringProperty(QueryableProperty):

        def get_value(self, obj):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)

Cached getter
^^^^^^^^^^^^^

Getters of queryable properties can be marked as cached, which will make them act similarly to properties decorated
with Python's/Django's ``cached_property`` decorator:
The getter's code will only be executed on the first access and then be stored, while subsequent calls of the getter
will retrieve the cached value (unless the property is reset on a model object, see below).

To use this feature with the decorator-based approach, simply pass the ``cached`` parameter with the value ``True`` to
the ``queryable_property`` constructor:

.. code-block:: python

    from queryable_properties.properties import queryable_property


    class ApplicationVersion(models.Model):
        ...

        @queryable_property(cached=True)
        def version_str(self):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=self.major, minor=self.minor)

Using the class-based approach, the class attribute ``cached`` can be set to ``True`` instead (it would also be
possible to set this attribute on individual instances of the queryable property instead):

.. code-block:: python

    from queryable_properties.properties import QueryableProperty


    class VersionStringProperty(QueryableProperty):

        cached = True

        def get_value(self, obj):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)

.. note::
   All queryable properties that implement annotation will act like cached properties on the result objects of a
   queryset after they have been explicitly selected.
   Read more about this in :ref:`annotations:Selecting annotations`.

Resetting a cached property
"""""""""""""""""""""""""""

If there's ever a need for an exception from using the cache functionality, the cached value of a queryable property
on a particular model instance can be reset at any time.
This means that the getter's code will be executed again on the next access and the result will be used as the new
cached value (since it's still a queryable property marked as cached).
To make this as simple as possible, a method ``reset_property``, which takes the name of a defined queryable property
as parameter, is automatically added to each model class that defines at least one queryable property.
If a model class already defines a method with this name, it will *not* be overridden.
Queryable properties on objects of such model classes may instead be cleared using the utility function
:func:`queryable_properties.utils.reset_queryable_property`.

To reset the ``version_str`` property from the example above on an ``ApplicationVersion`` instance, both of the
variants in the following code block can be used (``obj`` is an ``ApplicationVersion`` instance):

.. code-block:: python

    from queryable_properties.utils import reset_queryable_property  # Required for variant 2

    # Variant 1: using the automatically defined method
    obj.reset_property('version_str')

    # Variant 2: using the utility function
    reset_queryable_property(obj, 'version_str')

Setter
------

Setter methods can be defined in the exact same way as they would be on regular properties when using the
decorator-based approach:

.. code-block:: python

    from queryable_properties.properties import queryable_property


    class ApplicationVersion(models.Model):
        ...

        @queryable_property
        def version_str(self):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=self.major, minor=self.minor)

        @version_str.setter
        def version_str(self, value):
            """Set the version fields from a version string."""
            # Don't implement any validation to keep the example simple.
            self.major, self.minor = value.split('.')

Using the class-based approach, the queryable property's method ``set_value`` must be implemented instead, taking the
model object to set the fields on as well as the actual value for the property as parameters.
It is recommended to use the :class:`queryable_properties.properties.SetterMixin` for class-based queryable properties
that define a setter because it defines the actual stub for the ``set_value`` method.
However, using this mixin is not required - a queryable property can be set as long as the ``set_value`` method is
implemented correctly.

.. code-block:: python

    from queryable_properties.properties import QueryableProperty, SetterMixin


    class VersionStringProperty(SetterMixin, QueryableProperty):

        def get_value(self, obj):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)

        def set_value(self, obj, value):
            """Set the version fields from a version string."""
            # Don't implement any validation to keep the example simple.
            obj.major, obj.minor = value.split('.')

Setter cache behavior
^^^^^^^^^^^^^^^^^^^^^

Since queryable properties can be marked as cached, they also come with options regarding the interaction between
cached values and setters.

.. note::
   The setter cache behavior is not only relevant for queryable properties that have been marked as cached.
   Explicitly selected queryable property annotations also behave like cached properties, which means they also make
   use of this option if their setter is used after they were selected.
   Read more about this in :ref:`annotations:Selecting annotations`.

There are 4 options that can be used via constants (which in reality are functions, much like Django's built-in values
for the ``on_delete`` option of ``ForeignKey`` fields), which can be imported from ``queryable_properties.properties``:

``CLEAR_CACHE`` (default)
  After the setter is used, a cached value for this property on the model instance is reset.
  The next use of the getter will therefore execute the getter code again and then cache the new value (unless the
  property isn't actually marked as cached).

``CACHE_VALUE``
  After the setter is used, the cache for the queryable property on the model instance will be updated with the value
  that was passed to the setter.

``CACHE_RETURN_VALUE``
  Like ``CACHE_VALUE``, but the *return value* of the function decorated with ``@<property>.setter`` for the
  decorator-based approach or the ``set_value`` method for the class-based approach is cached instead.
  The function/method should therefore return a value when this option is used, as ``None`` will be cached on each
  setter usage otherwise.

``DO_NOTHING``
  As the name suggests, this behavior will not interact with cached values at all after a setter is used.
  This means that cached values from before the setter was used will remain in the cache and may therefore not reflect
  the most recent value.

To provide a simple example, the setter of the ``version_str`` property should now be extended to be able to accept
values starting with ``'V'`` (e.g. ``'V2.0'`` instead of just ``'2.0'``) and the newly set value should be cached after
the setter was used.
Using ``CACHE_VALUE`` is therefore not a viable option as it would simply cache the value passed to the setter, which
may or may not be prefixed with ``'V'``, making the getter unreliable as it would return these unprocessed values.
Instead, ``CACHE_RETURN_VALUE`` will be used to ensure the correct getter format for cached values.

To achieve this using the decorator-based approach, the ``cache_behavior`` parameter of the ``setter`` decorator must
be used:

.. code-block:: python

    from queryable_properties.properties import CACHE_RETURN_VALUE, queryable_property


    class ApplicationVersion(models.Model):
        ...

        @queryable_property(cached=True)
        def version_str(self):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=self.major, minor=self.minor)

        @version_str.setter(cache_behavior=CACHE_RETURN_VALUE)
        def version_str(self, value):
            """Set the version fields from a version string, which is allowed to be prefixed with 'V'."""
            # Don't implement any validation to keep the example simple.
            if value.lower().startswith('v'):
                value = value[1:]
            self.major, self.minor = value.split('.')
            return value  # This value will be cached due to CACHE_RETURN_VALUE

For the class-based approach, the class (or instance) attribute ``setter_cache_behavior`` must be set:

.. code-block:: python

    from queryable_properties.properties import CACHE_RETURN_VALUE, QueryableProperty, SetterMixin


    class VersionStringProperty(SetterMixin, QueryableProperty):

        cached = True
        setter_cache_behavior = CACHE_RETURN_VALUE

        def get_value(self, obj):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)

        def set_value(self, obj, value):
            """Set the version fields from a version string, which is allowed to be prefixed with 'V'."""
            # Don't implement any validation to keep the example simple.
            if value.lower().startswith('v'):
                value = value[1:]
            obj.major, obj.minor = value.split('.')
            return value  # This value will be cached due to CACHE_RETURN_VALUE

Deleter
-------

Unlike regular properties, queryable properties do *not* offer a deleter.
This is intentional as queryable properties are supposed to be based on model fields, which can't just be deleted from
a model instance either.
(Nullable) Fields can, however, be "cleared" by setting their value to ``None`` - but this can just as easily be
achieved by using a setter to set this value.
