"""
Throwaway host models used only by the test suite.

The toolkit ships no models that *use* a ``CloudflareImageField`` (that is the job
of the projects that install it), so the usage-registry tests need their own host
models. These live in the ``tests`` app (added to ``INSTALLED_APPS`` in
``tests/settings.py``); their tables are created via ``run_syncdb`` when the test
database is built. They deliberately cover the cases the registry must handle:
integer and UUID primary keys, multiple image fields on one model, and a model
with no image field at all.
"""

import uuid

from django.db import models

from django_cloudflareimages_toolkit.fields import CloudflareImageField


class Product(models.Model):
    """Integer-pk host with a single image field."""

    name = models.CharField(max_length=100, blank=True)
    image = CloudflareImageField(blank=True, null=True)


class Article(models.Model):
    """UUID-pk host with two image fields (exercises multi-field tracking)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=100, blank=True)
    cover = CloudflareImageField(blank=True, null=True)
    thumbnail = CloudflareImageField(blank=True, null=True)


class Plain(models.Model):
    """Host with no image field — must never be discovered or tracked."""

    name = models.CharField(max_length=100, blank=True)
