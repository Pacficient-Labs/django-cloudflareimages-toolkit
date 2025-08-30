"""
Django model fields for Cloudflare Images integration.

This module provides custom Django model fields that integrate seamlessly
with Cloudflare Images, handling upload URLs, validation, and image management.
"""

from typing import Any, Optional

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .models import CloudflareImage
from .services import cloudflare_service
from .widgets import CloudflareImageWidget


class CloudflareImageField(models.Field):
    """
    A Django model field for storing Cloudflare Images.

    This field stores the Cloudflare image ID and provides easy access
    to image URLs, variants, and metadata. It integrates with the
    CloudflareImage model and service layer.
    """

    description = _("Cloudflare Image")

    def __init__(
        self,
        variants: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        require_signed_urls: bool = False,
        max_file_size: int | None = None,
        allowed_formats: list[str] | None = None,
        **kwargs,
    ):
        """
        Initialize the CloudflareImageField.

        Args:
            variants: List of variant names to create for uploaded images
            metadata: Default metadata to attach to uploaded images
            require_signed_urls: Whether to require signed URLs for image access
            max_file_size: Maximum file size in bytes (None for no limit)
            allowed_formats: List of allowed image formats (jpeg, png, gif, webp)
            **kwargs: Additional field options
        """
        self.variants = variants or []
        self.metadata = metadata or {}
        self.require_signed_urls = require_signed_urls
        self.max_file_size = max_file_size
        self.allowed_formats = allowed_formats or ["jpeg", "png", "gif", "webp"]

        # Set default field options
        kwargs.setdefault("max_length", 255)
        kwargs.setdefault("blank", True)
        kwargs.setdefault("null", True)

        super().__init__(**kwargs)

    def get_internal_type(self) -> str:
        """Return the internal field type for Django."""
        return "CharField"

    def to_python(self, value: Any) -> Optional["CloudflareImageFieldValue"]:
        """
        Convert the database value to a Python object.

        Args:
            value: The value from the database (Cloudflare image ID)

        Returns:
            CloudflareImageFieldValue instance or None
        """
        if value is None or value == "":
            return None

        if isinstance(value, CloudflareImageFieldValue):
            return value

        # Value should be a Cloudflare image ID string
        if isinstance(value, str):
            return CloudflareImageFieldValue(value, field=self)

        raise ValidationError(
            _("Invalid value for CloudflareImageField: %(value)s"),
            params={"value": value},
        )

    def from_db_value(
        self, value: Any, expression, connection
    ) -> Optional["CloudflareImageFieldValue"]:
        """Convert database value to Python object."""
        return self.to_python(value)

    def get_prep_value(self, value: Any) -> str | None:
        """
        Convert Python object to database value.

        Args:
            value: CloudflareImageFieldValue instance or string

        Returns:
            Cloudflare image ID string or None
        """
        if value is None:
            return None

        if isinstance(value, CloudflareImageFieldValue):
            return value.cloudflare_id

        if isinstance(value, str):
            return value

        return str(value)

    def formfield(self, **kwargs) -> forms.Field:
        """Return the form field for this model field."""
        defaults = {
            "widget": CloudflareImageWidget(
                variants=self.variants,
                metadata=self.metadata,
                require_signed_urls=self.require_signed_urls,
                max_file_size=self.max_file_size,
                allowed_formats=self.allowed_formats,
            ),
            "required": not self.blank,
        }
        defaults.update(kwargs)
        return forms.CharField(**defaults)

    def validate(self, value: Any, model_instance) -> None:
        """Validate the field value."""
        super().validate(value, model_instance)

        if value and isinstance(value, CloudflareImageFieldValue):
            # Additional validation can be added here
            pass

    def deconstruct(self) -> tuple:
        """Return field definition for migrations."""
        name, path, args, kwargs = super().deconstruct()

        # Add custom field options to kwargs
        if self.variants:
            kwargs["variants"] = self.variants
        if self.metadata:
            kwargs["metadata"] = self.metadata
        if self.require_signed_urls:
            kwargs["require_signed_urls"] = self.require_signed_urls
        if self.max_file_size:
            kwargs["max_file_size"] = self.max_file_size
        if self.allowed_formats != ["jpeg", "png", "gif", "webp"]:
            kwargs["allowed_formats"] = self.allowed_formats

        return name, path, args, kwargs


class CloudflareImageFieldValue:
    """
    A wrapper class for Cloudflare image values.

    This class provides easy access to image URLs, variants, and metadata
    while storing only the Cloudflare image ID in the database.
    """

    def __init__(self, cloudflare_id: str, field: CloudflareImageField | None = None):
        """
        Initialize the field value.

        Args:
            cloudflare_id: The Cloudflare image ID
            field: The CloudflareImageField instance (optional)
        """
        self.cloudflare_id = cloudflare_id
        self.field = field
        self._cloudflare_image = None

    def __str__(self) -> str:
        """Return string representation."""
        return self.cloudflare_id

    def __bool__(self) -> bool:
        """Return True if image ID exists."""
        return bool(self.cloudflare_id)

    def __eq__(self, other) -> bool:
        """Check equality with another CloudflareImageFieldValue."""
        if isinstance(other, CloudflareImageFieldValue):
            return self.cloudflare_id == other.cloudflare_id
        if isinstance(other, str):
            return self.cloudflare_id == other
        return False

    @property
    def cloudflare_image(self) -> CloudflareImage | None:
        """
        Get the associated CloudflareImage model instance.

        Returns:
            CloudflareImage instance or None if not found
        """
        if self._cloudflare_image is None and self.cloudflare_id:
            try:
                self._cloudflare_image = CloudflareImage.objects.get(
                    cloudflare_id=self.cloudflare_id
                )
            except CloudflareImage.DoesNotExist:
                pass
        return self._cloudflare_image

    def get_url(self, variant: str = "public") -> str | None:
        """
        Get the image URL for a specific variant.

        Args:
            variant: The image variant name (default: 'public')

        Returns:
            Image URL string or None if not available
        """
        if not self.cloudflare_id:
            return None

        # Try to get URL from CloudflareImage model first
        if self.cloudflare_image:
            return self.cloudflare_image.public_url

        # Fallback to generating URL from service
        try:
            from .settings import cloudflare_settings

            account_id = cloudflare_settings.account_id

            if account_id:
                return f"https://imagedelivery.net/{account_id}/{self.cloudflare_id}/{variant}"
        except Exception:
            pass

        return None

    def get_signed_url(self, variant: str = "public", expiry: int = 3600) -> str | None:
        """
        Get a signed URL for the image.

        Args:
            variant: The image variant name
            expiry: URL expiry time in seconds

        Returns:
            Signed URL string or None if not available
        """
        # For now, return the regular URL since signed URLs aren't implemented in the model
        return self.get_url(variant)

    def delete(self) -> bool:
        """
        Delete the image from Cloudflare.

        Returns:
            True if deletion was successful, False otherwise
        """
        if not self.cloudflare_id:
            return False

        try:
            # Get the CloudflareImage instance first
            if self.cloudflare_image:
                result = cloudflare_service.delete_image(self.cloudflare_image)
                # The service returns a boolean, not a dict
                if result:
                    return True
            return False
        except Exception:
            return False

    def get_metadata(self) -> dict[str, Any]:
        """
        Get image metadata.

        Returns:
            Dictionary of image metadata
        """
        if self.cloudflare_image:
            return self.cloudflare_image.metadata
        return {}

    def update_metadata(self, metadata: dict[str, Any]) -> bool:
        """
        Update image metadata.

        Args:
            metadata: New metadata dictionary

        Returns:
            True if update was successful, False otherwise
        """
        if not self.cloudflare_id:
            return False

        try:
            # Update the CloudflareImage model instance if it exists
            if self.cloudflare_image:
                self.cloudflare_image.metadata.update(metadata)
                self.cloudflare_image.save()
                return True
            return False
        except Exception:
            return False

    @property
    def variants(self) -> list[str]:
        """
        Get available image variants.

        Returns:
            List of variant names
        """
        if self.cloudflare_image and self.cloudflare_image.variants:
            return list(self.cloudflare_image.variants)
        return []

    @property
    def file_size(self) -> int | None:
        """Get image file size in bytes."""
        if self.cloudflare_image:
            return self.cloudflare_image.file_size
        return None

    @property
    def filename(self) -> str | None:
        """Get original filename."""
        if self.cloudflare_image:
            return self.cloudflare_image.filename
        return None

    @property
    def uploaded_at(self):
        """Get upload timestamp."""
        if self.cloudflare_image:
            return self.cloudflare_image.uploaded_at
        return None

    @property
    def is_ready(self) -> bool:
        """Check if image processing is complete."""
        if self.cloudflare_image:
            return self.cloudflare_image.status == "uploaded"
        return False
