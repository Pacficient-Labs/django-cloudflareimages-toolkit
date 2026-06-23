"""
Django Cloudflare Images Toolkit

A comprehensive Django toolkit that provides secure image upload functionality,
transformations, and management using Cloudflare Images.
"""

__version__ = "1.1.0"
__author__ = "PacNPal"

# Always import Django-independent utilities
from .metadata import ImageMetadataFactory
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
        "ImageUsage": (".models", "ImageUsage"),
        "ImageUploadStatus": (".models", "ImageUploadStatus"),
        "cloudflare_service": (".services", "cloudflare_service"),
        "register_usage": (".registry", "register_usage"),
        "unregister_usage": (".registry", "unregister_usage"),
        "get_models_with_image_fields": (".registry", "get_models_with_image_fields"),
        "CloudflareImageField": (".fields", "CloudflareImageField"),
        "CloudflareImageWidget": (".widgets", "CloudflareImageWidget"),
        "CloudflareImagesError": (".exceptions", "CloudflareImagesError"),
        "CloudflareImagesAPIError": (".exceptions", "CloudflareImagesAPIError"),
        "ConfigurationError": (".exceptions", "ConfigurationError"),
        "ValidationError": (".exceptions", "ValidationError"),
        "UploadError": (".exceptions", "UploadError"),
        "ImageNotFoundError": (".exceptions", "ImageNotFoundError"),
        "ImageNotReadyError": (".exceptions", "ImageNotReadyError"),
        "ImageOwnershipError": (".exceptions", "ImageOwnershipError"),
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
    "ImageMetadataFactory",
    "CloudflareImage",
    "ImageUploadLog",
    "ImageUsage",
    "ImageUploadStatus",
    "cloudflare_service",
    "register_usage",
    "unregister_usage",
    "get_models_with_image_fields",
    "CloudflareImageField",
    "CloudflareImageWidget",
    "CloudflareImagesError",
    "CloudflareImagesAPIError",
    "ConfigurationError",
    "ValidationError",
    "UploadError",
    "ImageNotFoundError",
    "ImageNotReadyError",
    "ImageOwnershipError",
]
