Changelog
=========

master (unreleased)
-------------------

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
- Fixed unnecessary fields in GROUP BY clauses in querysets that don't return model instances (i.e. queries with
  ``.values()`` or ``.values_list()``) in Django versions below 1.8
- Fixed an infinite recursion when constructing the HAVING clause for annotation-based filters that are not an aggregate
  in Django 1.8

1.0.2 (2019-06-02)
------------------

- The ``lookup`` parameter of custom filter implementations of queryable properties will now receive the combined
  lookup string if multiple lookups/transforms are used at once instead of just the first lookup/transform
- Fixed the construction of GROUP BY clauses when annotating queryable properties based on aggregates
- Fixed the construction of HAVING clauses when annotating queryable properties based on aggregates in Django versions
  below 1.9
- Fixed the ability to pickle queries and querysets with queryable properties functionality in Django versions below
  1.6

1.0.1 (2019-05-11)
------------------

- Added support for Django 2.2

1.0.0 (2018-12-31)
------------------

- Initial release
