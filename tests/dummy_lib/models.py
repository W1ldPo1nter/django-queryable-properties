# -*- coding: utf-8 -*-

from django.db import models
from django.utils.translation import gettext_lazy as _

from queryable_properties.properties import MappingProperty, ValueCheckProperty


class ReleaseTypeModel(models.Model):
    ALPHA = 'a'
    BETA = 'b'
    STABLE = 's'
    RELEASE_TYPE_CHOICES = (
        (ALPHA, _('Alpha')),
        (BETA, _('Beta')),
        (STABLE, _('Stable')),
    )

    release_type = models.CharField(max_length=1, choices=RELEASE_TYPE_CHOICES, default=STABLE)

    is_alpha = ValueCheckProperty('release_type', ALPHA)
    is_beta = ValueCheckProperty('release_type', BETA)
    is_stable = ValueCheckProperty('release_type', STABLE)
    is_unstable = ValueCheckProperty('release_type', ALPHA, BETA)
    release_type_verbose_name = MappingProperty('release_type', models.CharField(null=True), RELEASE_TYPE_CHOICES)

    class Meta:
        abstract = True

    @classmethod
    def from_db(cls, db, field_names, values):
        new = super(ReleaseTypeModel, cls).from_db(db, field_names, values)
        new._test = cls.__name__
        return new
