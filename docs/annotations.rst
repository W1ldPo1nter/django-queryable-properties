Annotatable properties
======================

The most powerful feature of queryable properties can be unlocked if a property can be expressed as an annotation.
Since annotations in a queryset behave like regular fields, they automatically offer some advantages:

- They can be used for queryset filtering without the need to explicitly implement filter behavior - though queryable
  properties still offer the option to implement custom filtering, even if a property is annotatable.
- They can be used for queryset ordering.
- They can be selected (which is what normally happens when using ``QuerySet.annotate``), meaning their values are
  computed and returned by the database while still only executing a single query.
  This will lead to huge performance gains for properties whose getter would normally perform additional queries.

Implementation
--------------

Let's make the simple ``version_str`` property from previous examples annotatable. Using the decorator-based approach,
the property's ``annotater`` method must be used.

.. code-block:: python

    from django.db.models import Model, Value
    from django.db.models.functions import Concat
    from queryable_properties.properties import queryable_property


    class ApplicationVersion(Model):
        ...

        @queryable_property
        def version_str(self):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=self.major, minor=self.minor)

        @version_str.annotater
        @classmethod
        def version_str(cls):
            return Concat('major', Value('.'), 'minor')

.. note::
   The ``classmethod`` decorator is not required, but makes the function look more natural since it takes the model
   class as its first argument.

For the same implementation with the class-based approach, the ``get_annotation`` method of the property class must be
implemented instead.
It is recommended to use the ``AnnotationMixin`` for such properties (more about this below), but it is not required to
be used.

.. code-block:: python

    from django.db.models import Value
    from django.db.models.functions import Concat
    from queryable_properties.properties import AnnotationMixin, QueryableProperty


    class VersionStringProperty(AnnotationMixin, QueryableProperty):

        def get_value(self, obj):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)

        def get_annotation(self, cls):
            return Concat('major', Value('.'), 'minor')

In both cases, the function/method takes the model class as the single argument (useful to implement custom logic in
inheritance scenarios) and must return an annotation - anything that would normally be passed to a
``QuerySet.annotate`` call, like simple ``F`` objects, aggregates, ``Case`` expressions, ``Subquery`` expressions, etc.

.. note::
   The returned annotation object may reference the names of other annotatable queryable properties on the same model,
   which will be resolved accordingly.

The ``AnnotationMixin`` and custom filter implementations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Unlike the ``SetterMixin`` and the ``UpdateMixin``, the :class:`queryable_properties.properties.AnnotationMixin` does a
bit more than just define the stub for the ``get_annotation`` method:

- It automatically implements filtering via the ``get_filter`` method by simply creating ``Q`` objects that reference
  the annotation.
  It is therefore not necessary to implent filtering for an annotatable queryable property unless some additional
  custom logic is desired (applies to either approach).
- It sets the class attribute ``filter_requires_annotation`` of the property class to ``True``.
  As the name suggests, this attribute determines if the annotation must be present in a queryset to be able to use the
  filter and is therefore automatically set to ``True`` to make the default filter implementation mentioned in the
  previous point work.
  For decorator-based properties using the ``annotater`` decorator, it also automatically sets
  ``filter_requires_annotation`` to ``True`` unless another value was already set (see the next example).

.. caution::
   Since the ``AnnotationMixin`` simply implements the ``get_filter`` method as mentioned above, care must be taken
   when using other mixins (most notably the ``LookupFilterMixin`` - see
   :ref:`filters:Lookup-based filter functions/methods`) that override this method as well (the implementations
   override each other).
   
   This is also relevant for the decorator-based approach as these mixins are automatically added to such properties
   when they use annotations or lookup-based filters.
   The order of the mixins for the class-based approach or the used decorators for the decorator-based approach is
   therefore important in such cases (the mixin applied last wins).

If the filter implementation shown in the :ref:`filters:One-for-all filter function/method` part of the filtering
chapter (which does not require the annotation and should therefore be configured accordingly) was to be retained
despite annotating being implemented, the implementation could look like this using the decorator-based approach (note
the ``requires_annotation=False``):

.. code-block:: python

    from django.db.models import Model, Q, Value
    from django.db.models.functions import Concat
    from queryable_properties.properties import queryable_property


    class ApplicationVersion(Model):
        ...

        @queryable_property
        def version_str(self):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=self.major, minor=self.minor)

        @version_str.filter(requires_annotation=False)
        @classmethod
        def version_str(cls, lookup, value):
            if lookup != 'exact':  # Only allow equality checks for the simplicity of the example
                raise NotImplementedError()
            # Don't implement any validation to keep the example simple.
            major, minor = value.split('.')
            return Q(major=major, minor=minor)

        @version_str.annotater
        @classmethod
        def version_str(cls):
            return Concat('major', Value('.'), 'minor')

.. note::
   If lookup-based filters are used with the decorator-based approach, the ``requires_annotation`` value can be set on
   any method decorated with the ``filter`` decorator.
   If a value for this parameter is specified in multiple ``filter`` calls, the last one will be the one that will
   determine the final value since it's still a global flag for the filter behavior (regardless of lookup).

For the class-based approach, the class (or instance) attribute ``filter_requires_annotation`` must be changed instead:

.. code-block:: python

    from django.db.models import Q, Value
    from django.db.models.functions import Concat
    from queryable_properties.properties import AnnotationMixin, QueryableProperty


    class VersionStringProperty(AnnotationMixin, QueryableProperty):

        filter_requires_annotation = False

        def get_value(self, obj):
            """Return the combined version info as a string."""
            return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)

        def get_filter(self, cls, lookup, value):
            if lookup != 'exact':  # Only allow equality checks for the simplicity of the example
                raise NotImplementedError()
            # Don't implement any validation to keep the example simple.
            major, minor = value.split('.')
            return Q(major=major, minor=minor)

        def get_annotation(self, cls):
            return Concat('major', Value('.'), 'minor')

.. note::
   If a custom filter is implemented that does depend on the annotation (with ``filter_requires_annotation=True``), the
   name of the property itself can be referenced in the returned ``Q`` objects. It will then refer to the annotation
   for that property instead of leading to an infinite recursion while trying to resolve the property filter.

Automatic (non-selecting) annotation usage
------------------------------------------

Queryable properties that implement annotating can be used like regular model fields in various queryset operations
without the need to explicitly add the annotation to a queryset.
This is achieved by automatically adding a queryable property annotation to the queryset in a *non-selecting* way
whenever such a property is referenced by name, meaning the annotation's SQL expression will not be part of the
``SELECT`` clause.

These queryset operations can also be used on related models and include:

- Filtering with an implementation that requires annotation (see above), e.g.
  ``ApplicationVersion.objects.filter(version_str='2.0')`` or
  ``Application.objects.filter(versions__version_str='2.0)``
  for the first examples in this chapter.
- Ordering, e.g. ``ApplicationVersion.objects.order_by('-version_str')`` or
  ``Application.objects.order_by('-versions__version_str')``.
- Using the queryable property in another annotation or aggregation, e.g.
  ``ApplicationVersion.objects.annotate(same_value=F('version_str'))`` or
  ``Application.objects.annotate(related_value=F('versions__version_str'))``.

.. caution::
   In Django versions below 1.8, it was not possible to order by annotations without selecting them at the same time.
   Queryable property annotations therefore have to be automatically added in a *selecting* manner if they appear in
   an ``.order_by()`` call in those versions.
   
   In querysets that return model instances, this may have performance implications due to the additional columns that
   are queried, but the annotation values will be discarded when model instances are created.
   This is done because selected queryable properties behave differently (see below), and this behavior is meant to be
   consistent across all supported Django versions.
   
   The selection of the queryable property annotations in these scenarios may also affect queries with ``.distinct()``
   calls (since the ``DISTINCT`` clause also applies to the annotation) or ``.values()``/``.values_list()`` queries,
   which will return the annotation column in addition to the ones specified in ``.values()``/``.values_list()``.

Caution: the order of queryset operations still matters!
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When making use of the automatic annotation injection, keep in mind that this is only a convenience feature that simply
performs two operations: it adds the queryable property annotation to the queryset (similarly to manually calling
``.annotate()``) and then performs the operation that was actually called (filtering, ordering, etc.).
Therefore, the order of operations performed on querysets still matters when additionally dealing with other fields or
even other queryable properties.
A classic example for this is the |aggregation-order|_.

.. |aggregation-order| replace:: order of ``annotate()`` and ``filter()`` clauses when dealing with aggregates
.. _aggregation-order: https://docs.djangoproject.com/en/stable/topics/db/aggregation/#order-of-annotate-and-filter-clauses

This is even more important for operations performed on related objects as it may influence how ``JOIN`` ed tables are
reused (which is standard Django behavior and not a "problem" of queryable properties).
To provide an example for this, let's assume the ``version_str`` queryable property from the first examples in this
chapter in conjunction with the following query:

.. code-block:: python

    Application.objects.filter(versions__version_str='2.0', versions__major=2)

While the filter conditions themselves don't make much sense together, they both use the same relation to the version
objects and can therefore show the potential problem.
Depending on which of the conditions is processed first, the results will be different:

- If the ``major`` filter is applied first, the actions will be performed in this order:
  1. apply the ``major`` filter
  2. automatically add the ``version_str`` annotation
  3. apply the ``version_str`` filter
  
  This will lead to only joining the ``ApplicationVersion`` table once and therefore correctly resulting in the filter
  combined with ``AND`` that was most likely intended.
- If the ``version_str`` filter is applied first, the actions will be performed in this order:
  1. automatically add the ``version_str`` annotation
  2. apply the ``version_str`` filter
  3. apply the ``major`` filter
  
  This will lead to two independent ``JOIN``s of the ``ApplicationVersion`` table, where each condition will only be
  applied to one of the joined tables, leading to more duplicate results and essentially an ``OR`` conjunction of the
  filter conditions.

It may therefore be desirable to ensure that the conditions are applied in the correct order.
To make sure that the ``major`` condition will be applied first, multiple options are at hand:

.. code-block:: python

    from django.db.models import Q

    # Using separate filter calls
    Application.objects.filter(versions__major=2).filter(versions__version_str='2.0')
    # Combining Q objects to represent the AND conjunction
    Application.objects.filter(Q(versions__major=2) & Q(versions__version_str='2.0'))
    # Passing the keyword arguments in the correct order in Python versions that preserve their order (3.7 and above)
    Application.objects.filter(versions__major=2, versions__version_str='2.0')

Selecting annotations
---------------------

Whenever the actual values for queryable properties are to be retrieved while performing a query, they must be
explicitly selected using the ``select_properties`` method defined by the ``QueryablePropertiesManager`` and the
``QueryablePropertiesQuerySet(Mixin)``, which takes any number of queryable property names as its arguments.
When this method is used, the specified queryable property annotations will be added to the queryset in a *selecting*
manner, meaning the SQL representing an annotation will be part of the ``SELECT`` clause of the query.
For consistency, the ``select_properties`` method always has to be used to select a queryable property annotation -
even when using features like ``values`` or ``values_list`` (these methods will not automatically select queryable
properties).

The following example shows how to select the ``version_str`` property from the examples above:

.. code-block:: python

    for version in ApplicationVersion.objects.select_properties('version_str'):
        print(version.version_str)  # Uses the value directly from the query and does not call the getter

To be able to make use of this performance-oriented feature, **all explicitly selected queryable properties will always
behave like properties with a** :ref:`standard_features:Cached getter` on the model instances returned by the queryset.
If this wasn't the case, accessing uncached queryable properties on model instances would always execute their default
behavior: calling the getter.
This would make the selection of the annotations useless to begin with, as the getter would called regardless and no
performance gain could be achieved by the queryset operation.
By instead behaving like cached queryable properties, one can make use of the queried values, which will be cached for
any number of consecutive accesses of the property on model objects returned by the queryset.
If it is desired to not access the cached values anymore, the cached value can always be cleared as described in
:ref:`standard_features:Resetting a cached property`.

Queryable properties on related models
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Selecting the values of queryable property annotations is the one annotation-based feature that **does not** allow to
use queryable properties defined on related models.
Therefore, the following example (based on the ``version_str`` property from the examples above) will **not** work:

.. code-block:: python

    for app in Application.objects.select_properties('versions__version_str'):
        ...

This is intentional for the following reasons:

- Since the queryable property would be defined on another model, the actual annotation in the current queryset would
  have to use a different name.
  The only real option for this would be the whole relation path containing the ``__`` separator(s), e.g.
  ``versions__version_str`` in the example above, which would be quite weird and ugly.
- Depending on the type of the relation, getting queryable property values from related models would not always have a
  clear meaning.
  This is the case for all ...-to-many relations, where there would be multiple potential values to choose from.

There is, however, a way to get the annotation values from queryable properties of related models: Since manually added
annotations can refer to queryable property annotations even across relations, this can be used to actually select the
values.
In the simplest case, the property could simply be aliased using an ``F`` object:

.. code-block:: python

    from django.db.models import F

    for app in Application.objects.annotate(my_annotation=F('versions__version_str')):
        print(app.my_annotation)

This solves the problems mentioned above:

- You need to choose a name for the new annotation yourself (``my_annotation`` in the example), which eliminates
  potential weird and ugly annotation names.
- You will have to make sure that the related values in conjunction with the relation type make sense and yield the
  results you expect.

Regarding aggregate annotations across relations
------------------------------------------------

An annotatable queryable property that is implemented using an aggregate may return unexpected results when using it
from a related model in a queryset (regardless for explicit selection or automatic use) since no extended ``GROUP BY``
setup other than what Django would do on its own takes place.

Consider the following decorator-based example (the effect would be the same for a class-based property), where a
queryable property for the number of corresponding versions is added to the ``Application`` model:

.. code-block:: python

    from django.db.models import Count, Model
    from queryable_properties.properties import queryable_property


    class Application(Model):
        ...

        @queryable_property
        def version_count(self):
            return self.versions.count()

        @version_count.annotater
        @classmethod
        def version_count(cls):
            return Count('versions')

If there were 2 applications, one having 2 versions and the other having 3, the following queryset would return both of
these versions, since the annotation values would be 2 and 3, respectively:

.. code-block:: python

    Application.objects.filter(version_count__in=(2, 3))  # Finds both applications

If both of these applications would belong to the same category, one would probably expect that we following queryset
would find that category, since it has 2 applications that fit the filter conditions:

.. code-block:: python

    Category.objects.filter(applications__version_count__in=(2, 3))

However, this is **not** the case - this query will not return that category.
This is because the result of the annotation is basically the same as the following manual annotation:

.. code-block:: python

    from django.db.models import Count

    Category.objects.annotate(applications__version_count=Count('applications__versions'))

This means that the value ``applications__version_count`` for the category would be 5, since it simply counts all
versions that are associated with this category via an application at all.
The reason for this is that Django uses ``JOIN`` s and ``GROUP BY`` clauses in order to generate the aggregated values,
but they are not automatically grouped by application.
Instead, the ``GROUP BY`` clause only contains the columns of the ``Category`` model, leading to one total value per
category.

There are options to work around this when running into this problem:

- Use |aggregation-values|_ yourself.
  For the example above, a ``.values('pk', 'applications__pk')`` call before the ``.filter()`` call would be
  sufficient.
  Keep in mind that the same category can then be returned multiple times if more than one of its versions matches the
  filter condition.
- Do not directly use an aggregate like ``Count`` at all and count the versions per application using a
  `subquery <https://docs.djangoproject.com/en/stable/ref/models/expressions/#subquery-expressions>`_.
  This subquery will then also be performed correctly when the queryable property is used from a related model.

.. |aggregation-values| replace:: ``values()`` to set the ``GROUP BY`` clause
.. _aggregation-values: https://docs.djangoproject.com/en/stable/topics/db/aggregation/#values
