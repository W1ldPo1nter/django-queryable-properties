# Update queries

Queryable properties offer the option to use the names of properties in batch updates (i.e. when using the `update`
method of querysets).
To achieve this, the `update` argument for a queryable property will simply be translated into `update` values for
actual model fields.

Let's use the `version_str` of the `ApplicationVersion` model as an example once again.

To allow the usage of this queryable property in queryset updates using the decorator-based approach, the property's
`updater` method must be used.
```python
from queryable_properties.properties import queryable_property


class ApplicationVersion(models.Model):
    ...
    
    @queryable_property
    def version_str(self):
        """Return the combined version info as a string."""
        return '{major}.{minor}'.format(major=self.major, minor=self.minor)
    
    @version_str.updater
    @classmethod
    def version_str(cls, value):
        # Don't implement any validation to keep the example simple.
        major, minor = value.split('.')
        return {'major': major, 'minor': minor}
```

```eval_rst
.. note::
   The ``classmethod`` decorator is not required, but makes the function look more natural since it takes the model class
   as its first argument.
```

Using the class-based approach, the same thing can be achieved by implementing the `get_update_kwargs` method of the
property class.
It is recommended to use the `UpdateMixin` for class-based queryable properties that are supposed to be used in
queryset updates because it defines the actual stub for the `get_update_kwargs` method.
However, using this mixin is not required - a queryable property can be used for queryset updates as long as the 
`get_update_kwargs` method is implemented correctly.
```python
from queryable_properties.properties import QueryableProperty, UpdateMixin


class VersionStringProperty(UpdateMixin, QueryableProperty):

    def get_value(self, obj):
        """Return the combined version info as a string."""
        return '{major}.{minor}'.format(major=obj.major, minor=obj.minor)
    
    def get_update_kwargs(self, cls, value):
        # Don't implement any validation to keep the example simple.
        major, minor = value.split('.')
        return {'major': major, 'minor': minor}
```

In both cases, the function/method to implement takes 2 arguments:
- `cls`: The model class. Mainly useful to implement custom logic in inheritance scenarios.
- `value`: The value to update the database rows with.

Using either approach, the function/method is expected to return a `dict` object that contains the model field/value
combinations that are actually required to perform the update correctly.

```eval_rst
.. note::
   The returned ``dict`` object may contain name/value pairs referring to other queryable properties on the same model,
   which will be resolved accordingly in the same manner.
```

With both implementations, the queryable property can be used in queryset updates like this:
```python
ApplicationVersion.objects.update(version_str='1.1')
```

The specified value is then translated into actual field values by the implemented function/method and the real,
underlying `update` call will take place with these values.
