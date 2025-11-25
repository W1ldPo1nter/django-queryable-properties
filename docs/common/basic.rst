Properties evaluating field values
----------------------------------

The properties in this category are designed for very specific use cases that evaluate field values to check whether
certain conditions are met or to transform them into other values.
They are thus not based on annotations.

Attribute paths
^^^^^^^^^^^^^^^

To specify the fields whose values are to be evaluated, the properties in this category use *attribute paths* in their
arguments.
These are strings that typically contain a simple field name, but they can also contain more complex paths to
attributes using dot-notation - basically the same way as for Python's |operator.attrgetter|_.
For queryset operations, the dots are then simply replaced by the lookup separator (``__``), so an attribute path
``my.attr`` becomes ``my__attr`` in queries.

This is especially useful to reach fields of related model instances via foreign keys, but it also allows to be more
creative since the path simply needs to make sense both on the object-level as well as in queries.
For example, a ``DateField`` may be defined as ``date_field = models.DateField()``, which would allow a
``ValueCheckProperty`` to be set up with the path ``date_field.year``.
This works because the ``date`` object has an attribute ``year`` on the object-level and Django offers a ``year``
transform for querysets (so ``date_field__year`` does in fact work).
However, this specific example requires at least Django 1.9 as older versions don't allow to combine transforms and
lookups.
In general, this means that the attribute path does not have to refer to an actual field, which also means that it may
refer to another queryable property (which needs to support the ``in`` lookup to be able to filter correctly).

Unlike Python's |operator.attrgetter|_, the property will also automatically catch some exceptions during getter access
(if any of them occur, the property considers none of the configured values as matching):

- ``AttributeError`` s if an intermediate object is ``None`` (e.g. if a path is ``a.b`` and the ``a`` attribute already
  returns ``None``, then the attribute error when accessing ``b`` will be caught).
  This is intended to make working with nullable fields easier.
  Any other kind of ``AttributeError`` will still be raised.
- Any ``ObjectDoesNotExist`` errors raised by Django, which are raised e.g. when accessing a reverse One-To-One
  relation with a missing value.
  This is intended to make working with these kinds of relations easier.

.. |operator.attrgetter| replace:: ``operator.attrgetter``
.. _operator.attrgetter: https://docs.python.org/3/library/operator.html#operator.attrgetter

``ValueCheckProperty``
^^^^^^^^^^^^^^^^^^^^^^

Properties on model objects are often used to check if an attribute on a model instance contains a specific value (or
one of multiple values).
This is often done for fields with choices as it allows to implement the check for a certain choice value in one place
instead of redefining it whenever the field should be checked for the value.
However, the pattern is not limited to fields with choices.

Imagine that the ``ApplicationVersion`` example model would also contain a field that contains information about the
type of release, e.g. if a certain version is an alpha, a beta, etc.
It would be well-advised to use a field with choices for this value and to also define properties to check for the
individual values to only define these checks once.

Without *django-queryable-properties*, the implementation could look similar to this:

.. code-block:: python

    from django.db import models
    from django.utils.translation import ugettext_lazy as _


    class ApplicationVersion(models.Model):
        ALPHA = 'a'
        BETA = 'b'
        STABLE = 's'
        RELEASE_TYPE_CHOICES = (
            (ALPHA, _('Alpha')),
            (BETA, _('Beta')),
            (STABLE, _('Stable')),
        )

        ...  # other fields
        release_type = models.CharField(max_length=1, choices=RELEASE_TYPE_CHOICES)

        @property
        def is_alpha(self):
            return self.release_type == self.ALPHA

        @property
        def is_beta(self):
            return self.release_type == self.BETA

        @property
        def is_stable(self):
            return self.release_type == self.STABLE

        @property
        def is_unstable(self):
            return self.release_type in (self.ALPHA, self.BETA)

Instead of defining the properties like this, the property class
:class:`queryable_properties.properties.ValueCheckProperty` could be used:

.. code-block:: python

    from django.db import models
    from django.utils.translation import ugettext_lazy as _

    from queryable_properties.managers import QueryablePropertiesManager
    from queryable_properties.properties import ValueCheckProperty


    class ApplicationVersion(models.Model):
        ALPHA = 'a'
        BETA = 'b'
        STABLE = 's'
        RELEASE_TYPE_CHOICES = (
            (ALPHA, _('Alpha')),
            (BETA, _('Beta')),
            (STABLE, _('Stable')),
        )

        ...  # other fields
        release_type = models.CharField(max_length=1, choices=RELEASE_TYPE_CHOICES)

        objects = QueryablePropertiesManager()

        is_alpha = ValueCheckProperty('release_type', ALPHA)
        is_beta = ValueCheckProperty('release_type', BETA)
        is_stable = ValueCheckProperty('release_type', STABLE)
        is_unstable = ValueCheckProperty('release_type', ALPHA, BETA)

Instances of this property class take an attribute path (see :ref:`common/basic:Attribute paths`) to check as their
first parameter in addition to any number of parameters that represent the values to check for - if one of them matches
when the property is accessed on a model instance, the property will return ``True`` (otherwise ``False``).

Not only does this property class allow to achieve the same functionality with less code, but it offers even more
functionality due to being a *queryable* property.
The class implements both queryset filtering as well as annotating (based on Django's ``Case``/``When`` objects), so
the properties can be used in querysets as well:

.. code-block:: python

    stable_versions = ApplicationVersion.objects.filter(is_stable=True)
    non_alpha_versions = ApplicationVersion.objects.filter(is_alpha=False)
    ApplicationVersion.objects.order_by('is_unstable')

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``ValueCheckProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.ValueCheckProperty.__init__>`

   ``ValueCheckProperty`` offers the following queryable property features:

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

``RangeCheckProperty``
^^^^^^^^^^^^^^^^^^^^^^

A common pattern that uses a property is having a model with two attributes that define a lower and an upper limit and
a property that checks if a certain value is contained in that range.
These fields may be numerical fields (``IntegerField``, ``DecimalField``, etc.) or something like date fields
(``DateField``, ``DateTimeField``, etc.) - basically anything that allows "greater than" and "lower than" comparisons.

As an example, the ``ApplicationVersion`` example model could contain two such date fields to express the period in
which a certain app version is supported, which could look similar to this:

.. code-block:: python

    from django.db import models
    from django.utils import timezone


    class ApplicationVersion(models.Model):
        ...  # other fields
        supported_from = models.DateTimeField()
        supported_until = models.DateTimeField()

        @property
        def is_supported(self):
            return self.supported_from <= timezone.now() <= self.supported_until

Instead of defining the properties like this, the property class
:class:`queryable_properties.properties.RangeCheckProperty` could be used:

.. code-block:: python

    from django.db import models
    from django.utils import timezone

    from queryable_properties.managers import QueryablePropertiesManager
    from queryable_properties.properties import RangeCheckProperty


    class ApplicationVersion(models.Model):
        ...  # other fields
        supported_from = models.DateTimeField()
        supported_until = models.DateTimeField()

        objects = QueryablePropertiesManager()

        is_supported = RangeCheckProperty('supported_from', 'supported_until', timezone.now)

Instances of this property class take the :ref:`common/basic:Attribute paths` for the lower and upper limits as their
first and second arguments.
If one of the limiting values is ``None`` or an exception is caught, the value is considered missing (see next sub-
chapter).
The third mandatory parameter for ``RangeCheckProperty`` objects is the value to check against, which may either be a
static value or a callable that can be called without any argument and that returns the actual value (``timezone.now``
in the example above), similar to the ``default`` option of Django's model fields.

Not only does this property class allow to achieve the same functionality with less code, but it offers even more
functionality due to being a *queryable* property.
The class implements both queryset filtering as well as annotating (based on Django's ``Case``/``When`` objects), so the
properties can be used in querysets as well:

.. code-block:: python

    currently_supported = ApplicationVersion.objects.filter(is_supported=True)
    not_supported = ApplicationVersion.objects.filter(is_supported=False)
    ApplicationVersion.objects.order_by('is_supported')

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``RangeCheckProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.RangeCheckProperty.__init__>`

   ``RangeCheckProperty`` offers the following queryable property features:

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

Range configuration
"""""""""""""""""""

``RangeCheckProperty`` objects also allow further configuration to tweak the configured range via some optional
parameters:

``include_boundaries``
  Determines if a value exactly equal to one of the limits is considered a part of the range (default: ``True``).

``include_missing``
  Determines if a missing value for either boundary is considered part of the range (default: ``False``).

``in_range``
  Determines if the property should return ``True`` if the value is contained in the configured range (this is the
  default) or if it should return ``True`` if the value is outside of the range.

It should be noted that the ``include_boundaries`` and ``include_missing`` parameters are applied first to define the
range (which values are considered inside the range between the two values) and the ``in_range`` parameter is applied
*afterwards* to potentially invert the result (in the case of ``in_range=False``).
This means that setting ``include_missing=True`` defines that missing values are part of the range and a value of
``in_range=False`` would then invert this range, meaning that missing values would **not** lead to a value of ``True``
since they are configured to be in the range while the property is set up to return ``True`` for values outside of the
range.
For a quick reference, all possible configuration combinations are listed in the following table:

.. list-table::
   :header-rows: 1
   :widths: 15 15 15 55

   * - ``include_boundaries``
     - ``include_missing``
     - ``in_range``
     - returns ``True`` for
   * - ``True``
     - ``False``
     - ``True``
     - * Values in between boundaries (excl.)
       * The exact boundary values
   * - ``True``
     - ``True``
     - ``True``
     - * Values in between boundaries (excl.)
       * The exact boundary values
       * Missing values
   * - ``False``
     - ``False``
     - ``True``
     - * Values in between boundaries (excl.)
   * - ``False``
     - ``True``
     - ``True``
     - * Values in between boundaries (excl.)
       * Missing values
   * - ``True``
     - ``False``
     - ``False``
     - * Values outside of the boundaries (excl.)
       * Missing values
   * - ``True``
     - ``True``
     - ``False``
     - * Values outside of the boundaries (excl.)
   * - ``False``
     - ``False``
     - ``False``
     - * Values outside of the boundaries (excl.)
       * The exact boundary values
       * Missing values
   * - ``False``
     - ``True``
     - ``False``
     - * Values outside of the boundaries (excl.)
       * The exact boundary values

.. note::
   The attribute paths passed to ``RangeCheckProperty`` may also refer to other queryable properties as long as these
   properties allow filtering with the ``lt``/``lte`` and ``gt``/``gte`` lookups (depending on the value of
   ``include_boundaries``) and potentially the ``isnull`` lookup (depending on the value of ``include_missing``).

``MappingProperty``
^^^^^^^^^^^^^^^^^^^

The property class :class:`queryable_properties.properties.MappingProperty` streamlines a very simple pattern: mapping
the values of an attribute (most likely a field) to different values.
While there is nothing special about this on an object basis, it allows to introduce values into querysets that
otherwise are not database values.
The value mapping inside querysets is achieved using ``CASE``/``WHEN`` expressions based on Django's ``Case``/``When``
objects, which means that this property class can only be properly used in Django versions that provide these features
(1.8+).

A common use case for this might be to set up a ``MappingProperty`` that simply works with a choice field and uses the
choice definitions themselves as its mappings.
This allows to introduce the (most likely translatable) choice verbose names into the query, which in turn allows to
order the queryset by the *translated* verbose names, providing sensible ordering no matter what language an
application is used in.

For the release type values in an example above, this could look like this:

.. code-block:: python

    from django.db import models
    from django.utils.translation import ugettext_lazy as _

    from queryable_properties.managers import QueryablePropertiesManager
    from queryable_properties.properties import MappingProperty


    class ApplicationVersion(models.Model):
        ALPHA = 'a'
        BETA = 'b'
        STABLE = 's'
        RELEASE_TYPE_CHOICES = (
            (ALPHA, _('Alpha')),
            (BETA, _('Beta')),
            (STABLE, _('Stable')),
        )

        ...  # other fields
        release_type = models.CharField(max_length=1, choices=RELEASE_TYPE_CHOICES)

        objects = QueryablePropertiesManager()

        release_type_verbose_name = MappingProperty('release_type', models.CharField(), RELEASE_TYPE_CHOICES)

In a view, one could then perform a query similar to the following to order the ``ApplicationVersion`` objects by
their translated verbose name, which may lead to a different ordering depending on the user's language:

.. code-block:: python

    ApplicationVersion.objects.order_by('release_type_verbose_name')

This is, however, not the only way ``MappingProperty`` objects can be used - any attribute values may be translated
into any other values that can be represented in database queries and then used in querysets.

.. admonition:: Arguments and supported features

   Refer to the documentation of the ``MappingProperty`` initializer for a list of arguments:
   :py:class:`__init__<queryable_properties.properties.MappingProperty.__init__>`

   ``MappingProperty`` offers the following queryable property features:

   +------------+------------------------------------+
   | Feature    | Supported                          |
   +============+====================================+
   | Getter     | ✅ (all supported Django versions) |
   +------------+------------------------------------+
   | Setter     | ❌                                 |
   +------------+------------------------------------+
   | Filtering  | ✅ (**Django 1.8 or higher**)      |
   +------------+------------------------------------+
   | Annotation | ✅ (**Django 1.8 or higher**)      |
   +------------+------------------------------------+
   | Updating   | ❌                                 |
   +------------+------------------------------------+

.. note::
   Whenever the mapping output values are actually accessed (by accessing the property on an object or by referencing
   it in a queryset), lazy values (like the translations in the example above) are evaluated.
   Property access or queryset references should therefore be performed as late as possible when dealing with lazy
   mapping values.
   For queryset operations, the translated values are also automatically wrapped in
   `Value <https://docs.djangoproject.com/en/stable/ref/models/expressions/#value-expressions>`_ objects.

.. note::
   The attribute path passed to ``MappingProperty`` may also refer to another queryable property as long as this
   property allows filtering with the ``exact`` lookup.
