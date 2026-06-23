"""
Signal receivers that keep the ``ImageUsage`` index in sync with host models.

These are connected per tracked sender in
:meth:`~django_cloudflareimages_toolkit.apps.CloudflareImagesConfig.ready`, so
they only fire for models that actually declare a ``CloudflareImageField``. All
real work is delegated to the shared, idempotent helpers in :mod:`.registry`.
"""

from __future__ import annotations

from .registry import _db, clear_object, sync_object


def sync_instance_usage(sender, instance, using=None, **kwargs) -> None:
    """post_save: upsert/clear usage rows for a saved host instance.

    Django passes the database alias as ``using``; we forward it so multi-DB
    deployments record the usage on the same database as the host instance.
    """
    sync_object(instance, using=using)


def remove_instance_usage(sender, instance, using=None, **kwargs) -> None:
    """post_delete: drop all usage rows for a deleted host instance."""
    clear_object(instance, using=using)


def bump_image_on_usage_delete(sender, instance, using=None, **kwargs) -> None:
    """post_delete on ImageUsage: bump the affected image's last_referenced_at.

    A usage row deletion is the moment the image lost (one of) its references;
    that is when its orphan-retention clock should start. Without this bump, a
    long-referenced image whose reference is removed could be eligible for
    immediate orphan deletion (legacy data with ``last_referenced_at IS NULL``)
    or be judged against an old reference event rather than the actual moment
    it became unreferenced.
    """
    if instance.image_id is None:
        return
    from .registry import _bump_last_referenced

    _bump_last_referenced(instance.image_id, using=using)


def link_image_to_usages(sender, instance, using=None, **kwargs) -> None:
    """post_save on CloudflareImage: backfill the FK on matching unlinked usages.

    When an image referenced before its ``CloudflareImage`` record existed is later
    registered, link the previously "unregistered" usage rows to it and mark the
    image as referenced now (so orphan-retention treats the link as a fresh
    reference rather than basing the clock on its upload time).
    """
    from .models import ImageUsage
    from .registry import _bump_last_referenced

    linked = (
        ImageUsage.objects.using(_db(using))
        .filter(cloudflare_id=instance.cloudflare_id, image__isnull=True)
        .update(image=instance)
    )
    if linked:
        _bump_last_referenced(instance, using=using)
