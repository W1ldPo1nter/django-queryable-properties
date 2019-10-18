# Common Patterns

*django-queryable-properties* offers some fully implemented properties for common code patterns out of the box.
They are parameterizable and are supposed to help remove boilerplate for recurring types of properties while making
them usable in querysets at the same time.

## Checking a field for one or multiple specific values

Properties on model objects are often used to check if a field on a model instance contains a specific value (or one 
of multiple values).
This is often done for fields with choices as it allows to implement the check for a certain choice value in one place
instead of redefining it whenever the field should be checked for the value.
However, the pattern is not limited to fields with choices.

Imagine that the `ApplicationVersion` example model would also contain a field that contains information about the type
of release, e.g. if a certain version is an alpha, a beta, etc.
It would be well-advised to use a field with choices for this value and to also define properties to check for the
individual values to only define these checks once.

Without *django-queryable-properties*, the implementation could look similar to this:
```python
from django.db import models
from django.utils.translation import ugettext_lazy as _


class ApplicationVersion(models.Model):
    ALPHA = 'a'
    BETA = 'b'
    STABLE = 's'
    RELEASE_TYPE_CHOICES = (
        (ALPHA, _('Alpha')),
        (BETA, _('Beta')),
        (STABLE, _('Stable')),
    )

    ...  # other fields
    release_type = models.CharField(max_length=1, choices=RELEASE_TYPE_CHOICES)
    
    @property
    def is_alpha(self):
        return self.release_type == self.ALPHA
    
    @property
    def is_beta(self):
        return self.release_type == self.BETA
    
    @property
    def is_stable(self):
        return self.release_type == self.STABLE
    
    @property
    def is_unstable(self):
        return self.release_type in (self.ALPHA, self.BETA)
```

Instead of defining the properties like this, the property class `ValueCheckProperty` of the
*django-queryable-properties* could be used:
```python
from django.db import models
from django.utils.translation import ugettext_lazy as _

from queryable_properties.properties import ValueCheckProperty


class ApplicationVersion(models.Model):
    ALPHA = 'a'
    BETA = 'b'
    STABLE = 's'
    RELEASE_TYPE_CHOICES = (
        (ALPHA, _('Alpha')),
        (BETA, _('Beta')),
        (STABLE, _('Stable')),
    )

    ...  # other fields
    release_type = models.CharField(max_length=1, choices=RELEASE_TYPE_CHOICES)
    
    is_alpha = ValueCheckProperty('release_type', ALPHA)
    is_beta = ValueCheckProperty('release_type', BETA)
    is_stable = ValueCheckProperty('release_type', STABLE)
    is_unstable = ValueCheckProperty('release_type', ALPHA, BETA)
```

Instances of this property class take the name of the field to check as their first parameters in addition to any
number of parameters that represent the values to check for - if one of them matches when the property is accessed on
a model instance, the property will return `True` (otherwise `False`).

Not only does this property class allow to achieve the same functionality with less code, but it offers even more
functionality due to being a *queryable* property.
The class implements both queryset filtering as well as annotating (based on Django's `Case`/`When` objects), so the
properties can be used in querysets as well:
```python
stable_versions = ApplicationVersion.objects.filter(is_stable=True)
non_alpha_versions = ApplicationVersion.objects.filter(is_alpha=False)
ApplicationVersion.objects.order_by('is_unstable')
```

For a quick overview, the `ValueCheckProperty` offers the following queryable property features:
```eval_rst
+----------------+----------------------------+
| Feature        | Supported                  |
+================+============================+
| Getter         | Yes                        |
+----------------+----------------------------+
| Setter         | No                         |
+----------------+----------------------------+
| Filtering      | Yes                        |
+----------------+----------------------------+
| Annotation     | Yes (Django 1.8 or higher) |
+----------------+----------------------------+
| Updating       | No                         |
+----------------+----------------------------+

.. note::
   The field name passed to ``ValueCheckProperty`` may also refer to another queryable property as long as that
   property allows filtering with the ``in`` lookup.
```
