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
   because an annotated field in a queryset natively supports filtering. Read more about this in the documentation for
   :doc:`annotatable queryable properties <annotations>`.
```

To implement (custom) filtering using the decorator-based approach, the property's `filter` method must be used.
The following code block contains an example for the `version_str` property from previous examples:
```python
from django.db.models import Q
from queryable_properties.properties import queryable_property


class ApplicationVersion(models.Model):
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
   The ``classmethod`` decorator is not required, but makes the function look more natural since it takes the model class
   as its first argument.
```

To implement (custom) filtering using the class-based apprach, the `get_filter` method must be implemented. The
following code block contains an example for the `version_str` property from previous examples:
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
- `cls`: The model class. Mainly useful to implement custom logic in inheritance scenarios.
- `lookup`: The lookup used for the filter as a string (e.g. `'lt'` or `'contains'`). If a filter call is made without
  an explicit lookup for an equality comparison (e.g. via `ApplicationVersion.objects.filter(version_str='2.0')`), the
  lookup will be `'exact'`.
- `value`: The value to filter by.

Using either approach, the function/method is expected to return a `Q` object that contains the correct filter
conditions to represent filtering by the queryable property using the given lookup and value.

```eval_rst
.. note::
   The returned ``Q`` object may contain filters using other queryable properties on the same model, which will be
   resolved accordingly.
```

With both implementations, the queryable property can be used to filter querysets like this:
```python
ApplicationVersion.objects.filter(version_str='1.1')
ApplicationVersion.objects.exclude(version_str='1.2')
...
```

These filters may also be combined with filters for other fields or queryable properties and can also be used in nested
filter expressions using `Q` objects, i.e. the queryable properties can be treated like regular model fields.
