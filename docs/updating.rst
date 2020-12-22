Update queries
==============

Queryable properties offer the option to use the names of properties in batch updates (i.e. when using the ``update``
method of querysets).
To achieve this, the ``update`` value for a queryable property will simply be translated into ``update`` values for
actual model fields.

Implementation
--------------

Let's use the ``version_str`` of the ``ApplicationVersion`` model as an example once again.

To allow the usage of this queryable property in queryset updates using the decorator-based approach, the property's
``updater`` method must be used.

.. code-block:: python

    from queryable_properties.properties import queryable_property


    class ApplicationVersion(models.Model):
        ...

        @queryable_property
        def version_str(self):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=self.major, minor=self.minor)

        @version_str.updater
        @classmethod
        def version_str(cls, value):
            # Don't implement any validation to keep the example simple.
            major, minor = value.split('.')
            return {'major': major, 'minor': minor}

.. note::
   The ``classmethod`` decorator is not required, but makes the function look more natural since it takes the model
   class as its first argument.

Using the class-based approach, the same thing can be achieved by implementing the ``get_update_kwargs`` method of the
property class.
It is recommended to use the :class:`queryable_properties.properties.UpdateMixin` for class-based queryable properties
that are supposed to be used in queryset updates because it defines the actual stub for the ``get_update_kwargs``
method.
However, using this mixin is not required - a queryable property can be used for queryset updates as long as the 
``get_update_kwargs`` method is implemented correctly.

.. code-block:: python

    from queryable_properties.properties import QueryableProperty, UpdateMixin


    class VersionStringProperty(UpdateMixin, QueryableProperty):

        def get_value(self, obj):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)

        def get_update_kwargs(self, cls, value):
            # Don't implement any validation to keep the example simple.
            major, minor = value.split('.')
            return {'major': major, 'minor': minor}

In both cases, the function/method to implement takes 2 arguments:

``cls``
  The model class. Mainly useful to implement custom logic in inheritance scenarios.

``value``
  The value to update the database rows with.

Using either approach, the function/method is expected to return a ``dict`` object that contains the model field/value
combinations that are actually required to perform the update correctly.

.. note::
   The returned ``dict`` object may contain name/value pairs referring to other queryable properties on the same model,
   which will be resolved accordingly in the same manner.

Usage
-----

With both implementations, the queryable property can be used in queryset updates like this:

.. code-block:: python

    ApplicationVersion.objects.update(version_str='1.1')

The specified value is then translated into actual field values by the implemented function/method and the real,
underlying ``update`` call will take place with these values.

Limitations
-----------

Related models
^^^^^^^^^^^^^^

Unlike filtering and annotation-based operations, updating can not be used for fields on related models.
This is because updates are generally meant for records of the same type to be able to perform an ``UPDATE`` query on a
single table (aside from inheritance scenarios, where Django takes care of updating multiple tables correctly).
*django-queryable-properties* doesn't add any additional logic here and simply translates the given value according
to the updater implementation and therefore doesn't allow updating fields on related models, either.

Expression-based update values
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Using expression-based values (like an ``F`` objects or a
`conditional update <https://docs.djangoproject.com/en/stable/ref/models/conditional-expressions/#conditional-update>`_)
are generally not supported when updating via a queryable property.
This is because the queryable property updater is simply a preprocessor for the ``.update(...)`` keyword arguments on
the python side, while expression-based updates rely on other values in the query, which are only evaluated in SQL when
the query actually runs.

However, *django-queryable-properties* doesn't technically prevent to use expressions as update values.
This means that if an expression is used as an update value, it will be passed through to the method decorated with
``updater`` (decorator-based approach) or the ``get_update_kwargs`` implementation (class-based approach).
Therefore it would technically be possible to process an expression in the updater's implementation as long the
expression can be preprocessed in a sensible way before the query runs.
