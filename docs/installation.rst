Installation
============

*django-queryable-properties* is available for installation via ``pip`` on PyPI::

    pip install django-queryable-properties

To use the features of this package, simply use the classes and functions as described in this documentation.
There is no need to add the package to the ``INSTALLED_APPS`` setting.

Dependencies
------------

*django-queryable-properties* supports and is tested against the following Django versions and their corresponding
supported Python versions:

+----------------+----------------------------+
| Django version | Supported Python versions  |
+================+============================+
| 5.2            | 3.13, 3.12, 3.11, 3.10     |
+----------------+----------------------------+
| 5.1            | 3.13, 3.12, 3.11, 3.10     |
+----------------+----------------------------+
| 5.0            | 3.12, 3.11, 3.10           |
+----------------+----------------------------+
| 4.2            | 3.12, 3.11, 3.10, 3.9, 3.8 |
+----------------+----------------------------+
| 4.1            | 3.11, 3.10, 3.9, 3.8       |
+----------------+----------------------------+
| 4.0            | 3.10, 3.9, 3.8             |
+----------------+----------------------------+
| 3.2            | 3.10, 3.9, 3.8, 3.7, 3.6   |
+----------------+----------------------------+
| 3.1            | 3.9, 3.8, 3.7, 3.6         |
+----------------+----------------------------+
| 3.0            | 3.9, 3.8, 3.7, 3.6         |
+----------------+----------------------------+
| 2.2            | 3.9, 3.8, 3.7, 3.6, 3.5    |
+----------------+----------------------------+
| 2.1            | 3.7, 3.6, 3.5              |
+----------------+----------------------------+
| 2.0            | 3.7, 3.6, 3.5              |
+----------------+----------------------------+
| 1.11           | 3.7, 3.6, 3.5, 2.7         |
+----------------+----------------------------+
| 1.10           | 3.5, 2.7                   |
+----------------+----------------------------+
| 1.9            | 3.5, 2.7                   |
+----------------+----------------------------+
| 1.8            | 3.5, 2.7                   |
+----------------+----------------------------+
| 1.7            | 2.7                        |
+----------------+----------------------------+
| 1.6            | 2.7                        |
+----------------+----------------------------+
| 1.5            | 2.7                        |
+----------------+----------------------------+
| 1.4            | 2.7                        |
+----------------+----------------------------+

Support for certain Python versions was added to some Django versions retrospectively in a patch version.
The tests run against the most recent patch version for each Django release.

Upcoming versions may also work, but are not officially supported as long as they are not added to the test setup.
