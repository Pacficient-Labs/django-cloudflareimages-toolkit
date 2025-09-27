"""
Django Cloudflare Images Toolkit

A comprehensive Django toolkit that provides secure image upload functionality,
transformations, and management using Cloudflare Images.
"""

__version__ = "1.0.8"
__author__ = "PacNPal"

# Always import transformation utilities (Django-independent)
from .transformations import (
    CloudflareImageTransform,
    CloudflareImageUtils,
    CloudflareImageVariants,
)

# Try to import Django-dependent components
try:
    from .exceptions import (
        CloudflareImagesAPIError,
        CloudflareImagesError,
        ConfigurationError,
        ImageNotFoundError,
        UploadError,
        ValidationError,
    )
    from .fields import CloudflareImageField
    from .models import CloudflareImage, ImageUploadLog, ImageUploadStatus
    from .services import cloudflare_service
    from .widgets import CloudflareImageWidget

    _django_available = True
except (ImportError, Exception):
    # Django not configured or not available
    _django_available = False
    CloudflareImage = None
    ImageUploadLog = None
    ImageUploadStatus = None
    cloudflare_service = None
    CloudflareImageField = None
    CloudflareImageWidget = None
    CloudflareImagesError = None
    CloudflareImagesAPIError = None
    ConfigurationError = None
    ValidationError = None
    UploadError = None
    ImageNotFoundError = None

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
            "CloudflareImageField",
            "CloudflareImageWidget",
            "CloudflareImagesError",
            "CloudflareImagesAPIError",
            "ConfigurationError",
            "ValidationError",
            "UploadError",
            "ImageNotFoundError",
        ]
    )
