Admin integration
=================

*django-queryable-properties* comes with an integration in Django's admin, allowing to use queryable properties in
various places in both ``ModelAdmin`` subclasses and inlines.
To properly get queryable properties to work with certain features of admins/inlines, *django-queryable-properties*
offers specialized base classes that can be used instead of Django's regular base classes:

* :class:`queryable_properties.admin.QueryablePropertiesAdmin` in place of Django's
  `ModelAdmin <https://docs.djangoproject.com/en/stable/ref/contrib/admin/#django.contrib.admin.ModelAdmin>`_
* :class:`queryable_properties.admin.QueryablePropertiesStackedInline` in place of Django's
  `StackedInline <https://docs.djangoproject.com/en/stable/ref/contrib/admin/#django.contrib.admin.StackedInline>`_
* :class:`queryable_properties.admin.QueryablePropertiesTabularInline` in place of Django's
  `TabularInline <https://docs.djangoproject.com/en/stable/ref/contrib/admin/#django.contrib.admin.TabularInline>`_

For more complex inheritance scenarios, there is also the
:class:`queryable_properties.admin.QueryablePropertiesAdminMixin`, which can be added to both admin and inline classes
to enable queryable properties functionality while using different admin/inline base classes.

The following table shows the admin/inline options that queryable properties may be referenced in and whether each
feature requires the use of one of the specialized base classes mentioned above.
Queryable properties may be refenced via name in either the listed admin/inline class attributes or in the result of
their corresponding ``get_*`` methods.

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Admin/inline option
     - Requires special class
     - Restrictions/Remarks
   * - ``fields``/``fieldsets``
     - No
     - * For properties with a getter or selected properties only
       * Properties must also be part of ``readonly_fields``
   * - ``list_display``
     - * No for properties on the same model
       * Yes for properties on related models (requires Django 1.8 or higher)
     - * Properties on the same model must have a getter or be selected
       * Properties on related models must be annotatable
   * - ``list_display_links``
     - See ``list_display``
     - * For properties with a getter or selected properties only
   * - ``list_filter``
     - Yes
     - * For annotatable properties only
       * Properties must support the lookups used by their list filter class (which is automatically the case if no
         custom filtering is implemented)
       * When using the tuple form, the same list filter classes as for regular fields are used, but not all of
         Django's filter classes are supported as some of them may perform queries that are incompatible with
         queryable properties
   * - ``list_select_properties``
     - Yes
     - * Custom attribute/method of the specialized admin classes listed above
       * Takes a sequence of queryable property names that will automatically be selected via ``select_properties``
         (see :ref:`annotations:Selecting annotations`).
       * For annotatable properties only
   * - ``ordering``
     - Yes
     - * For annotatable properties only
   * - ``readonly_fields``
     - No
     - * For properties with a getter or selected properties only
   * - ``sortable_by``
     - No
     - * For annotatable properties only
   * - ``search_fields``
     - See ``list_display``
     - * Requires Django 2.1 or higher
       * Properties must support the lookup used by their respective entry in ``search_fields``
