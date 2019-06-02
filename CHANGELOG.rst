Changelog
=========

master (unreleased)
-------------------

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
