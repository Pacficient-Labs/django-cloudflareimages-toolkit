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
        """Initialize the app when Django starts."""
        # Import signal handlers if any
        pass
