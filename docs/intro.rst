Introduction
============

*django-queryable-properties* attempts to offer a unified pattern to help with a common and recurring problem:

#. Properties are added to a model class which are based on model field values of its instances.
   These properties may even be based on some related model objects and therefore perform additional database queries.
#. The code base grows and needs to be able to meet new requirements.
#. The logic of the properties from step 1 would now be useful in batch operations (read: queryset operations), making
   the current implementation less feasible, as it would likely perform additional queries per object in a queryset
   operation.
   Also, regular properties do of course not offer queryset features like filtering, ordering, etc.

Since Django offers a lot of powerful options when working with querysets (like ``select_related``, annotations, etc.),
it is generally not an issue to solve these problems and implement a solution, which will likely be based on one of the
following options:

- Performing special annotations only in the exact places that they are needed or in utility functions/methods.
- Implementing a custom model manager/queryset class to allow the usage of these special annotations whenever dealing
  with a queryset.
- Using ``queryset.alias()`` to build up a collection of available queryset annotations that resemble the properties
  (requires Django 3.2 or higher).

While especially the latter options are not *wrong*, they do require some boilerplate and will likely split up the
business logic into multiple parts (e.g. the property for single objects is implemented on the model class while
the corresponding annotation for batch operations is part of a queryset class), making it harder to apply changes to
the business logic to all required parts.
Solutions like these are genereally also not really reusable unless a lot of effort is put into them.
For example, even manager/queryset extensions will likely only work on the exact model they were designed for and will
therefore not be usable from other models via relations.

.. important::
   Starting with Django 5.0,
   `GeneratedFields <https://docs.djangoproject.com/en/stable/ref/models/fields/#generatedfield>`_ may be used to cover
   many of the use-cases of *django-queryable-properties*.
   Since they are native Django fields, the disadvantages mentioned above do not apply to them.

*django-queryable-properties* does, in fact, not remove the general necessity of implementing the business logic in
(at least) 2 parts - one for individual objects and one for batch/queryset operations.
Instead, it aims to remove as much boilerplate as possible and offers an option to implement said parts in one place -
just like the ``getter`` and ``setter`` of a regular property are implemented together.
On top of that, queryable properties cannot only be used in querysets for the model they were defined on, but can also
be accessed through relations when querying via other models.

Examples in this documentation
------------------------------

All parts of this documentation contain a few simple examples to show how to take advantage of all the features of
queryable properties.
For consistency, all of those examples are based on a few simple Django models, which are shown in the following code
block.
They represent models storing data for a version management system for applications, which in this over-simplified case
only store which versions of an application exist.
While this may not be the best real-world example, it can demonstrate how to work with queryable properties quite well.

.. code-block:: python

   from django.db import models


   class Category(models.Model):
       """Represents a category for applications."""
       name = models.CharField(max_length=255)


   class Application(models.Model):
       """Represents a named application."""
       categories = models.ManyToManyField(Category, related_name='applications')
       name = models.CharField(max_length=255)


   class ApplicationVersion(models.Model):
       """Represents a version of an application using a major and minor version number."""
       application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='versions')
       major = models.PositiveIntegerField()
       minor = models.PositiveIntegerField()
