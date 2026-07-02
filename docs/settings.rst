Settings
========

The behavior of *django-queryable-properties* can be configured using the following Django settings.

``QUERYABLE_PROPERTIES_APPLY_FETCH_MODE`` (default: ``False``)
  In Django 6.1+, this setting can be used to configure whether accessing annotatable queryable properties whose
  values haven't already been populated invokes the
  `fetch mode <https://docs.djangoproject.com/en/stable/topics/db/fetch-modes/>`_ of the queryset the model instances
  have been queried with.
  When enabled, applying a fetch mode will affect annotatable queryable properties in addition to relation fields
  and deferred fields.
  Refer to :ref:`annotations:Applying fetch modes to queryable properties` for more information.
