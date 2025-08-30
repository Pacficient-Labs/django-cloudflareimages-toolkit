"""
Django Cloudflare Images Toolkit

A comprehensive Django toolkit that provides secure image upload functionality,
transformations, and management using Cloudflare Images.
"""

__version__ = "1.0.0"
__author__ = "PacNPal"

# Always import transformation utilities (Django-independent)
from .transformations import (
    CloudflareImageTransform,
    CloudflareImageUtils,
    CloudflareImageVariants,
)

# Try to import Django-dependent components
try:
    from .models import CloudflareImage, ImageUploadLog, ImageUploadStatus
    from .services import CloudflareImagesError, cloudflare_service

    _django_available = True
except (ImportError, Exception):
    # Django not configured or not available
    _django_available = False
    CloudflareImage = None
    ImageUploadLog = None
    ImageUploadStatus = None
    cloudflare_service = None
    CloudflareImagesError = None

# Define what gets imported with "from django_cloudflareimages_toolkit import *"
__all__ = [
    "CloudflareImageTransform",
    "CloudflareImageVariants",
    "CloudflareImageUtils",
]

# Add Django components if available
if _django_available:
    __all__.extend(
        [
            "CloudflareImage",
            "ImageUploadLog",
            "ImageUploadStatus",
            "cloudflare_service",
            "CloudflareImagesError",
        ]
    )
