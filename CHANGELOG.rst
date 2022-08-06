Changelog
=========

master (unreleased)
-------------------

1.8.3 (2022-08-06)
------------------

- Added support for Django 4.1

1.8.2 (2022-06-08)
------------------

- Fixed queryset cloning in conjunction with positional arguments in Django versions below 1.9

1.8.1 (2022-03-05)
------------------

- Fixed erroneous transformations of querysets with queryable properties functionality into ``.values()`` querysets
  under rare circumstances in Django versions above 3.0
- Fixed the ability to pickle ``.values()``/``.values_list()`` querysets with queryable properties functionality in
  Django versions below 1.9
- Fixed the erroneous inclusion of values of queryable properties that are used for ordering without being explicitly
  selected in ``.values()``/``.values_list()`` querysets in Django versions below 1.8

1.8.0 (2021-12-07)
------------------

- Added support for Django 4.0
- Added new ready-to-use queryable property implementations for properties based on subqueries
  (``SubqueryFieldProperty``, ``SubqueryExistenceCheckProperty``)
- ``RelatedExistenceCheckProperty`` objects can now be configured as negated to be able to check for the non-existence
  of related objects

1.7.1 (2021-11-01)
------------------

- Added support for Python 3.10
- Fixed duplicate selections of ``GROUP BY`` columns when multiple aggregate properties are selected, which also led to
  wrong property values, in Django versions below 1.8

1.7.0 (2021-07-05)
------------------

- Added the ``prefetch_queryable_properties`` utility function which allows to efficiently query property values for
  model instances that were already loaded from the database beforehand
- Extended the ``LookupFilterMixin`` to allow to define a filter function/method that handles all lookups that don't
  use an explicitly registered function/method
- Values for queryable properties with setters can now also be set using initializer keyword arguments of their
  respective models

1.6.1 (2021-04-19)
------------------

- Fixed the ``AnnotationGetterMixin`` and its subclasses to be able to work with nested properties correctly regardless
  of whether or not the model's base manager uses the queryable properties extensions
- Fixed the admin filter that displays all possible options to be able to work with nested properties correctly
  regardless of whether or not the model's default manager uses the queryable properties extensions

1.6.0 (2021-04-06)
------------------

- Added support for Django 3.2
- Queryable properties can now define a verbose name that can be used in UI representations
- Added a Django admin integration that allows to reference queryable properties like regular model fields in various
  admin options
- Fixed the construction of ``GROUP BY`` clauses when using annotations based on aggregate queryable properties in
  Django 1.8

1.5.0 (2020-12-30)
------------------

- Added an option to implement annotation-based properties that use their annotation to query their getter value from
  the database
- Added a new ready-to-use queryable property implementation for properties that check whether or not certain related
  objects exist (``RelatedExistenceCheckProperty``)
- Added a new ready-to-use queryable property implementation for properties that map field/attribute values to other
  values (``MappingProperty``)

1.4.1 (2020-10-21)
------------------

- String representations of queryable properties do now contain the full Python path instead of the Django model path
  (also fixes an error that occurred when building the string representation for a property on an abstract model that
  was defined outside of the installed apps)

1.4.0 (2020-10-17)
------------------

- ``ValueCheckProperty`` and ``RangeCheckProperty`` objects can now take more complex attribute paths instead of simple
  field/attribute names
- ``RangeCheckProperty`` objects now have an option that determines how to treat missing values to support ranges with
  optional boundaries
- Added a new ready-to-use queryable property implementation for properties based on simple aggregates
  (``AggregateProperty``)

1.3.1 (2020-08-04)
------------------

- Added support for Django 3.1
- Refactored decorator-based properties to be more maintainable and memory-efficient and documented a way to use them
  without actually decorating

1.3.0 (2020-05-22)
------------------

- Added an option to implement simplified custom boolean filters utilizing lookup-based filters
- Fixed the ability to use the ``classmethod`` or ``staticmethod`` decorators with lookup-based filter methods for
  decorator-based properties
- Fixed the queryable property resolution in ``When`` parts of conditional updates
- Fixed the ability to use conditional expressions directly in ``.filter``/``.exclude`` calls in Django 3.0

1.2.1 (2019-12-03)
------------------

- Added support for Django 3.0

1.2.0 (2019-10-21)
------------------

- Added a mixin that allows custom filters for queryable properties (both class- and decorator-based) to be implemented
  using multiple functions/methods for different lookups
- Added some ready-to-use queryable property implementations (``ValueCheckProperty``, ``RangeCheckProperty``) to
  simplify common code patterns
- Added a standalone version of six to the package requirements

1.1.0 (2019-06-23)
------------------

- Queryable property filters (both annotation-based and custom) can now be used across relations when filtering
  querysets (i.e. a queryset can now be filtered by a queryable property on a related model)
- Queryset annotations can now refer to annotatable queryable properties defined on a related model
- Querysets can now be ordered by annotatable queryable properties defined on a related model
- Filters and annotations that reference annotatable queryable properties will not select the queryable property
  annotation anymore in Django versions below 1.8 (ordering by such a property will still lead to a selection in these
  versions)
- Fixed unnecessary selections of queryable property annotations in querysets that don't return model instances (i.e.
  queries with ``.values()`` or ``.values_list()``)
- Fixed unnecessary fields in ``GROUP BY`` clauses in querysets that don't return model instances (i.e. queries with
  ``.values()`` or ``.values_list()``) in Django versions below 1.8
- Fixed an infinite recursion when constructing the ``HAVING`` clause for annotation-based filters that are not an
  aggregate in Django 1.8

1.0.2 (2019-06-02)
------------------

- The ``lookup`` parameter of custom filter implementations of queryable properties will now receive the combined
  lookup string if multiple lookups/transforms are used at once instead of just the first lookup/transform
- Fixed the construction of ``GROUP BY`` clauses when annotating queryable properties based on aggregates
- Fixed the construction of ``HAVING`` clauses when annotating queryable properties based on aggregates in Django
  versions below 1.9
- Fixed the ability to pickle queries and querysets with queryable properties functionality in Django versions below
  1.6

1.0.1 (2019-05-11)
------------------

- Added support for Django 2.2

1.0.0 (2018-12-31)
------------------

- Initial release
