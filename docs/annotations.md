# Annotatable properties

The most powerful feature of queryable properties can be unlocked if a property can be expressed as an annotation.
Since annotations in a queryset behave like regular fields, they automatically offer some advantages:
- They can be used for queryset filtering without the need to explicitly implement filter behavior - though queryable
  properties still offer the option to implement custom filtering, even if a property is annotatable.
- They can be used for queryset ordering.
- They can be selected (which is what normally happens when using `QuerySet.annotate`), meaning their values are
  computed and returned by the database while still only executing a single query.
  This will lead to huge performance gains for properties whose getter would normally perform additional queries.

Let's make the simple `version_str` property from previous examples annotatable. Using the the decorator-based approach,
the property's `annotater` method must be used.
```python
from django.db.models import Model, Value
from django.db.models.functions import Concat
from queryable_properties import queryable_property


class ApplicationVersion(Model):
    ...
    
    @queryable_property
    def version_str(self):
        """Return the combined version info as a string."""
        return '{major}.{minor}'.format(major=self.major, minor=self.minor)
    
    @version_str.annotater
    @classmethod
    def version_str(cls, lookup, value):
        return Concat('major', Value('.'), 'minor')
```

```eval_rst
.. note::
   The ``classmethod`` decorator is not required, but makes the function look more natural since it takes the model class
   as its first argument.
```

For the same implementation with the class-based approach, the `get_annotation` method of the property class must be
implemented instead.
It is recommended to use the `AnnotationMixin` for such properties (more about this below), but it is not required to
be used.

```python
from django.db.models import Value
from django.db.models.functions import Concat
from queryable_properties import AnnotationMixin, QueryableProperty


class VersionStringProperty(AnnotationMixin, QueryableProperty):

    def get_value(self, obj):
        """Return the combined version info as a string."""
        return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)
    
    def get_annotation(self, cls):
        return Concat('major', Value('.'), 'minor')
```

In both cases, the function/method takes the model class as the single argument (useful to implement custom logic in
inheritance scenarios) and must return an annotation - anything that would normally be passed to a `QuerySet.annotate`
call, like simple `F` objects, aggregations, `Case` expressions, `Subquery` expressions, etc.

```eval_rst
.. note::
   The returned annotation object may reference the names of other annotatable queryable properties on the same model,
   which will be resolved accordingly.
```

## The `AnnotationMixin` and custom filter implementations

Unlike the `SetterMixin` and the `UpdateMixin`, the `AnnotationMixin` does a bit more than just define the stub for the
`get_annotation` method:
- It automatically implements filtering via the `get_filter` method by simply creating `Q` objects that reference the
  annotation.
  It is therefore not necessary to implent filtering for an annotatable queryable property unless some additional
  custom logic is desired (applies to either approach).
- It sets the class attribute `filter_requires_annotation` of the property class to `True`.
  As the name suggests, this attribute determines if the annotation must be present in a queryset to be able to use the
  filter and is therefore automatically set to `True` to make the default filter implementation mentioned in the
  previous point work.

Because of this, the `AnnotationMixin` is not only relevant for the class-based approach.
It will also be dynamically mixed into any decorator-based property that uses the `annotater` decorator and doesn't
implement filtering on its own.
For decorator-based properties using the `annotater` decorator, it also automatically sets `filter_requires_annotation`
to `True` unless another value was specified (see the following example).

If the filter implementation shown in the [filtering chapter](filters.md) (which does not require the annotation and should
therefore be configured accordingly) was to be retained despite annotating being implemented, the implementation could
look like this using the decorator-based approach (note the `requires_annotation=False`):
```python
from django.db.models import Model, Q, Value
from django.db.models.functions import Concat
from queryable_properties import queryable_property


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
    def version_str(cls, lookup, value):
        return Concat('major', Value('.'), 'minor')
```

For the class-based approach, the class (or instance) attribute `filter_requires_annotation` must be changed instead:
```python
from django.db.models import Q, Value
from django.db.models.functions import Concat
from queryable_properties import AnnotationMixin, QueryableProperty


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
```

```eval_rst
.. note::
   If a custom filter is implemented that does depend on the annotation (with ``filter_requires_annotation=True``), the
   name of the property itself can be referenced in the returned ``Q`` objects. It will then refer to the annotation
   for that property instead of leading to an infinite recursion while trying to resolve the property filter.
```

## Automatic (non-selecting) annotation usage

Queryable properties that implement annotating can be used like regular model fields in various queryset operations
without the need to explicitly add the annotation to a queryset.
This is achieved by automatically adding a queryable property annotation to the queryset in a *non-selecting* way
whenever such a property is referenced by name, meaning the annotation's SQL expression will not be part of the
`SELECT` clause.

These queryset operations include:
* Filtering with an implementation that requires annotation (see above), e.g. 
  `ApplicationVersion.objects.filter(version_str='2.0')` for the first examples in this chapter.
* Ordering, e.g. `ApplicationVersion.objects.order_by('-version_str')`.
* Using the queryable property in another annotation or aggregation, e.g.
  `ApplicationVersion.objects.annotate(same_value=F('version_str'))`.

```eval_rst
.. note::
   In Django versions below 1.8, selected and non-selected annotations were not as clearly distinguished as they are
   in more recent versions. Queryable property annotations therefore have to be automatically added in a *selecting*
   manner for the scenarios above in those versions (which may have performance implications due to the additional
   columns that are queried), but their values will be discarded when model instances are created. This is done because
   selected queryable properties behave differently (see below), which shouldn't unexpectedly happen in some Django
   versions.
```

## Selecting annotations

Whenever the actual values for queryable properties are to be retrieved while performing a query, they must be
explicitly selected using the `select_properties` method defined by the `QueryablePropertiesManager` and the
`QueryablePropertiesQuerySet(Mixin)`, which takes any number of queryable property names as its arguments.
When this method is used, the specified queryable property annotations will be added to the queryset in a *selecting*
manner, meaning the SQL representing an annotation will be part of the `SELECT` clause of the query.
For consistency, the `select_properties` method always has to be used to select a queryable property annotation -
even when using features like `values` or `values_list` (these methods will not automatically select queryable
properties).

The following example shows how to select the `version_str` property from the examples above:

```python
for version in ApplicationVersion.objects.select_properties('version_str'):
    print(version.version_str)  # Uses the value directly from the query and does not call the getter
```

To be able to make use of this performance-oriented feature, **all explicitly selected queryable properties will always
behave like [cached queryable properties](standard_features.md)** on the model instances returned by the queryset.
If this wasn't the case, accessing uncached queryable properties on model instances would always execute their default
behavior: calling the getter.
This would make the selection of the annotations useless to begin with, as the getter would called regardless and no
performance gain could be achieved by the queryset operation.
By instead behaving like cached queryable properties, one can make use of the queried values, which will be cached for
any number of consecutive accesses of the property on model objects returned by the queryset.
If it is desired to not access the cached values anymore, the cached value can always be cleared as described in
[Resetting a cached property](standard_features.md).
