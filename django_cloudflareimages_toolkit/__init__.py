"""
Django Cloudflare Images Toolkit

A comprehensive Django toolkit that provides secure image upload functionality,
transformations, and management using Cloudflare Images.
"""

__version__ = "1.0.9"
__author__ = "PacNPal"

# Always import transformation utilities (Django-independent)
from .transformations import (
    CloudflareImageTransform,
    CloudflareImageUtils,
    CloudflareImageVariants,
)


def __getattr__(name):
    """
    Lazy import of Django-dependent components.

    This allows the package to be imported before Django is configured,
    and only loads Django components when they're actually accessed.
    """
    django_components = {
        "CloudflareImage": (".models", "CloudflareImage"),
        "ImageUploadLog": (".models", "ImageUploadLog"),
        "ImageUploadStatus": (".models", "ImageUploadStatus"),
        "cloudflare_service": (".services", "cloudflare_service"),
        "CloudflareImageField": (".fields", "CloudflareImageField"),
        "CloudflareImageWidget": (".widgets", "CloudflareImageWidget"),
        "CloudflareImagesError": (".exceptions", "CloudflareImagesError"),
        "CloudflareImagesAPIError": (".exceptions", "CloudflareImagesAPIError"),
        "ConfigurationError": (".exceptions", "ConfigurationError"),
        "ValidationError": (".exceptions", "ValidationError"),
        "UploadError": (".exceptions", "UploadError"),
        "ImageNotFoundError": (".exceptions", "ImageNotFoundError"),
    }

    if name in django_components:
        module_name, attr_name = django_components[name]
        from importlib import import_module

        module = import_module(module_name, package=__name__)
        return getattr(module, attr_name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Define what gets imported with "from django_cloudflareimages_toolkit import *"
__all__ = [
    "CloudflareImageTransform",
    "CloudflareImageVariants",
    "CloudflareImageUtils",
    "CloudflareImage",
    "ImageUploadLog",
    "ImageUploadStatus",
    "cloudflare_service",
    "CloudflareImageField",
    "CloudflareImageWidget",
    "CloudflareImagesError",
    "CloudflareImagesAPIError",
    "ConfigurationError",
    "ValidationError",
    "UploadError",
    "ImageNotFoundError",
]
