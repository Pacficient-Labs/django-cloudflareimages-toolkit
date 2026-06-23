"""
Signal receivers that keep the ``ImageUsage`` index in sync with host models.

These are connected per tracked sender in
:meth:`~django_cloudflareimages_toolkit.apps.CloudflareImagesConfig.ready`, so
they only fire for models that actually declare a ``CloudflareImageField``. All
real work is delegated to the shared, idempotent helpers in :mod:`.registry`.
"""

from __future__ import annotations

from .registry import clear_object, sync_object


def sync_instance_usage(sender, instance, **kwargs) -> None:
    """post_save: upsert/clear usage rows for a saved host instance."""
    sync_object(instance)


def remove_instance_usage(sender, instance, **kwargs) -> None:
    """post_delete: drop all usage rows for a deleted host instance."""
    clear_object(instance)


def link_image_to_usages(sender, instance, **kwargs) -> None:
    """post_save on CloudflareImage: backfill the FK on matching unlinked usages.

    When an image referenced before its ``CloudflareImage`` record existed is later
    registered, link the previously "unregistered" usage rows to it.
    """
    from .models import ImageUsage

    ImageUsage.objects.filter(
        cloudflare_id=instance.cloudflare_id, image__isnull=True
    ).update(image=instance)
