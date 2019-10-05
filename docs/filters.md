# Filtering querysets

One of the most basic demands for a queryable property is the ability to be able to use it to filter querysets.
Since it is considered the most basic queryset interaction, filtering is thought of as a default part of every
queryable property.
The class-based approach does therefore not offer a mixin for this operation - the `QueryableProperty` base class
defines the method stub already.
This does, however, not mean that filtering *must* be implemented - a queryable property works fine without
implementing it, as long as we don't try to filter a queryset by such a property.

```eval_rst
.. note::
   Implementing how to filter by a queryable property is not necessary for properties that also implement annotating,
   because an annotated field in a queryset natively supports filtering.
   Read more about this in the documentation for :doc:`annotatable queryable properties <annotations>`.
```

## Implementation

### One-for-all filter function/method

The simplest way to implement (custom) filtering is using a single function/method that covers all filter
functionality.

To implement the one-for-all filter using the decorator-based approach, the property's `filter` method must be used.
The following code block contains an example for the `version_str` property from previous examples:
```python
from django.db.models import Model, Q
from queryable_properties.properties import queryable_property


class ApplicationVersion(Model):
    ...
    
    @queryable_property
    def version_str(self):
        """Return the combined version info as a string."""
        return '{major}.{minor}'.format(major=self.major, minor=self.minor)
    
    @version_str.filter
    @classmethod
    def version_str(cls, lookup, value):
        if lookup != 'exact':  # Only allow equality checks for the simplicity of the example
            raise NotImplementedError()
        # Don't implement any validation to keep the example simple.
        major, minor = value.split('.')
        return Q(major=major, minor=minor)
```

```eval_rst
.. note::
   The ``classmethod`` decorator is not required, but makes the function look more natural since it takes the model
   class as its first argument.
```

To implement the one-for-all filter using the class-based apprach, the `get_filter` method must be implemented.
The following code block contains an example for the `version_str` property from previous examples:
```python
from django.db.models import Q
from queryable_properties.properties import QueryableProperty


class VersionStringProperty(QueryableProperty):

    def get_value(self, obj):
        """Return the combined version info as a string."""
        return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)
    
    def get_filter(self, cls, lookup, value):
        if lookup != 'exact':  # Only allow equality checks for the simplicity of the example
            raise NotImplementedError()
        # Don't implement any validation to keep the example simple.
        major, minor = value.split('.')
        return Q(major=major, minor=minor)
```

In both cases, the function/method to implement takes 3 arguments:
- `cls`:
  The model class. Mainly useful to implement custom logic in inheritance scenarios.
- `lookup`: 
  The lookup used for the filter as a string (e.g. `'lt'` or `'contains'`).
  If a filter call is made without an explicit lookup for an equality comparison
  (e.g. via `ApplicationVersion.objects.filter(version_str='2.0')`), the lookup will be `'exact'`.
  If a filter call is made with multiple lookups/transforms (like `field__year__gt` for a date field), the lookup will
  be the combined string of all lookups/transforms (`'year__gt'` for the date example).
- `value`:
  The value to filter by.

Using either approach, the function/method is expected to return a `Q` object that contains the correct filter
conditions to represent filtering by the queryable property using the given lookup and value.

```eval_rst
.. note::
   The returned ``Q`` object may contain filters using other queryable properties on the same model, which will be
   resolved accordingly.
```

### Lookup-based filter functions/methods

When trying support a lot of different lookups for a (custom) filter implementation, the one-for-all filter can quickly
become unwieldy as it will most likely require a big `if`/`elif`/`else` dispatching structure.
To avoid this, *django-queryable-properties* also offers a built-in way to spread the filter implementation across
multiple functions or methods while assigning one or more lookups to each of them.
This can also be useful for implementations that only support a single lookup as it will guarantee that the filter can
only be called with this lookup, while a `QueryablePropertyError` will be raised for any other lookup.

Let's assume that the implementation above should also support the `lt` and `lte` lookups.
To achieve this with lookup-based filter functions using the decorator-based approach, the `lookups` argument of the
`filter` must be used:
```python
from django.db.models import Model, Q
from queryable_properties.properties import queryable_property


class ApplicationVersion(Model):
    ...
    
    @queryable_property
    def version_str(self):
        """Return the combined version info as a string."""
        return '{major}.{minor}'.format(major=self.major, minor=self.minor)
    
    @version_str.filter(lookups=('exact',))
    @classmethod
    def version_str(cls, lookup, value):  # Only ever called with the 'exact' lookup.
        # Don't implement any validation to keep the example simple.
        major, minor = value.split('.')
        return Q(major=major, minor=minor)
    
    @version_str.filter(lookups=('lt', 'lte'))
    @classmethod
    def version_str(cls, lookup, value):  # Only ever called with the 'lt' or 'lte' lookup.
        # Don't implement any validation to keep the example simple.
        major, minor = value.split('.')
        return Q(major__lt=major) | Q(**{'major': major, 'minor__{}'.format(lookup): minor})
```

```eval_rst
.. note::
   The ``classmethod`` decorator is not required, but makes the functions look more natural since they take the model
   class as their first argument.
```

To make use of the lookup-based filters using the class-based approach, the `LookupFilterMixin` (which implements
`get_filter`) must be used in conjunction with the `lookup_filter` decorator for the individual filter methods:
```python
from django.db.models import Q
from queryable_properties.properties import LookupFilterMixin, lookup_filter, QueryableProperty


class VersionStringProperty(LookupFilterMixin, QueryableProperty):

    def get_value(self, obj):
        """Return the combined version info as a string."""
        return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)
    
    @lookup_filter('exact')  # Alternatively: @LookupFilterMixin.lookup_filter(...)
    def filter_equality(self, cls, lookup, value):  # Only ever called with the 'exact' lookup.
        # Don't implement any validation to keep the example simple.
        major, minor = value.split('.')
        return Q(major=major, minor=minor)
    
    @lookup_filter('lt', 'lte')  # Alternatively: @LookupFilterMixin.lookup_filter(...)
    def filter_lower(self, cls, lookup, value):  # Only ever called with the 'lt' or 'lte' lookup.
        # Don't implement any validation to keep the example simple.
        major, minor = value.split('.')
        return Q(major__lt=major) | Q(**{'major': major, 'minor__{}'.format(lookup): minor})
```

For either approach, the individual filter functions/methods must take the same arguments as a one-for-all filter
implementation (see above) and return `Q` objects.
To support complex lookups (i.e. combinations of transforms and lookups), the full combined lookup string for each
supported option must be specified in the decorators (e.g. `'year__gt'`)

```eval_rst
.. caution::
   Since the ``LookupFilterMixin`` simply implements the ``get_filter`` method to perform the lookup dispatching, care
   must be taken when using other mixins (most notably the ``AnnotationMixin`` - see :doc:`annotations <annotations>`)
   that override this method as well (the implementations override each other).
   
   This is also relevant for the decorator-based approach as these mixins are automatically added to such properties
   when they use annotations or lookup-based filters.
   The order of the mixins for the class-based approach or the used decorators for the decorator-based approach is
   therefore important in such cases (the mixin applied last wins).
```

## Usage

With both implementations shown above, the queryable property can be used to filter querysets like any regular model
field:
```python
from django.db.models import Q

ApplicationVersion.objects.filter(version_str='1.1')
ApplicationVersion.objects.exclude(version_str__exact='1.2')
ApplicationVersion.objects.filter(application__name='My App', version_str='2.0')
ApplicationVersion.objects.filter(Q(version_str='1.9') | Q(major=2))
...
```

In the same manner, the filter can even be used when filtering on related models, e.g. when making queries from the
`Application` model:
```python
from django.db.models import Q

Application.objects.filter(versions__version_str='1.1')
Application.objects.exclude(versions__version_str__exact='1.2')
Application.objects.filter(name='My App', versions__version_str='2.0')
Application.objects.filter(Q(versions__major=2) | Q(versions__version_str='1.9'))
...
```
