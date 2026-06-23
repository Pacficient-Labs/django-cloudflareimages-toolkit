"""
Django app configuration for Cloudflare Images Toolkit.
"""

from django.apps import AppConfig


class CloudflareImagesConfig(AppConfig):
    """App configuration for django_cloudflareimages_toolkit."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_cloudflareimages_toolkit"
    verbose_name = "Cloudflare Images Toolkit"

    def ready(self):
        """Wire the image-usage registry when Django starts.

        Discover every model that declares a ``CloudflareImageField`` and connect
        usage-sync signals to those senders only (keeping the receivers off
        untracked models). ``dispatch_uid`` makes the wiring itself idempotent.
        """
        from django.db.models.signals import post_delete, post_save

        from . import signals
        from .models import CloudflareImage, ImageUsage
        from .registry import get_models_with_image_fields

        for model in get_models_with_image_fields():
            label = model._meta.label
            post_save.connect(
                signals.sync_instance_usage,
                sender=model,
                dispatch_uid=f"cfimg_usage_save_{label}",
            )
            post_delete.connect(
                signals.remove_instance_usage,
                sender=model,
                dispatch_uid=f"cfimg_usage_delete_{label}",
            )

        post_save.connect(
            signals.link_image_to_usages,
            sender=CloudflareImage,
            dispatch_uid="cfimg_link_usages",
        )
        # Mark the affected image's last_referenced_at whenever any usage row is
        # removed (whatever the deletion path: sync_object, clear_object,
        # unregister_usage, admin, or a raw ORM delete).
        post_delete.connect(
            signals.bump_image_on_usage_delete,
            sender=ImageUsage,
            dispatch_uid="cfimg_bump_image_on_usage_delete",
        )
