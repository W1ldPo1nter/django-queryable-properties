# -*- coding: utf-8 -*-

from django.db import models

from queryable_properties.properties import ValueCheckProperty


class ReleaseTypeModel(models.Model):
    ALPHA = 'a'
    BETA = 'b'
    STABLE = 's'
    RELEASE_TYPE_CHOICES = (
        (ALPHA, 'Alpha'),
        (BETA, 'Beta'),
        (STABLE, 'Stable'),
    )

    release_type = models.CharField(max_length=1, choices=RELEASE_TYPE_CHOICES, default=STABLE)

    is_alpha = ValueCheckProperty('release_type', ALPHA)
    is_beta = ValueCheckProperty('release_type', BETA)
    is_stable = ValueCheckProperty('release_type', STABLE)
    is_unstable = ValueCheckProperty('release_type', ALPHA, BETA)

    class Meta:
        abstract = True
