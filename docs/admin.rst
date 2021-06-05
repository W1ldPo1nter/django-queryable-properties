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

The following table shows the admin/inline options that queryable properties may be referenced in and whether or not
each feature requires the use of one of the specialized base classes mentioned above.
Queryable properties may be refenced via name in either the listed admin/inline class attributes or in the result of
their corresponding ``get_*`` methods (although there is a special case for ``get_list_filter`` as described in
:ref:`admin:Dynamically generating list filters` below).

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
     - No
     - * For properties with a getter or selected properties only
   * - ``list_display_links``
     - No
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
     - No
     - * Requires Django 2.1 or higher
       * Properties must support the lookup used by their respective entry in ``search_fields``

Dynamically generating list filters
-----------------------------------

Whenever the list filters are to be determined dynamically by overriding ``get_list_filter``, proper handling of
queryable property items may be disabled as this is also implemented by overriding ``get_list_filter``.
Therefore, it is important either invoke the queryable property processing by either generating the base filters
using a ``super`` call:

.. code-block:: python

    from queryable_properties.admin import QueryablePropertiesAdmin


    class MyAdmin(QueryablePropertiesAdmin):

        def get_list_filter(self, request):
            list_filter = super(MyAdmin, self).get_list_filter(request)
            # ... process the list filter sequence ...
            # Note: queryable property entries have been replaced with custom callables at this point.
            return list_filter


... or by utilizing the admin method
:meth:`queryable_properties.admin.QueryablePropertiesAdminMixin.process_queryable_property_filters` to postprocess a
custom generated filter sequence:

.. code-block:: python

    from queryable_properties.admin import QueryablePropertiesAdmin


    class MyAdmin(QueryablePropertiesAdmin):

        def get_list_filter(self, request):
            list_filter = []
            # ... generate the list filter sequence ...
            # Utilize process_queryable_property_filters to handle queryable property filters correctly.
            return self.process_queryable_property_filters(list_filter)
