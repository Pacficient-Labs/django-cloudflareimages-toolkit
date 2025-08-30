"""
Django models for Cloudflare Images Toolkit.

This module contains the database models for tracking image uploads,
transformations, and their status throughout the upload process.
"""

import uuid
from typing import Any

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class ImageUploadStatus(models.TextChoices):
    """Status choices for image uploads."""

    PENDING = "pending", "Pending"
    DRAFT = "draft", "Draft"
    UPLOADED = "uploaded", "Uploaded"
    FAILED = "failed", "Failed"
    EXPIRED = "expired", "Expired"


class CloudflareImage(models.Model):
    """Model to track Cloudflare image uploads."""

    # Primary identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cloudflare_id = models.CharField(max_length=255, unique=True, db_index=True)

    # User and metadata
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="cloudflare_images",
        null=True,
        blank=True,
    )
    filename = models.CharField(max_length=255, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)

    # Upload details
    upload_url = models.URLField(max_length=500)
    status = models.CharField(
        max_length=20,
        choices=ImageUploadStatus.choices,
        default=ImageUploadStatus.PENDING,
    )

    # Cloudflare settings
    require_signed_urls = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    uploaded_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    # Image dimensions and format
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    format = models.CharField(max_length=10, blank=True)

    # Cloudflare response data
    variants = models.JSONField(default=list, blank=True)
    cloudflare_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "cloudflare_images"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"CloudflareImage({self.cloudflare_id}) - {self.status}"

    @property
    def is_expired(self) -> bool:
        """Check if the upload URL has expired."""
        return timezone.now() > self.expires_at

    @property
    def is_uploaded(self) -> bool:
        """Check if the image has been successfully uploaded."""
        return self.status == ImageUploadStatus.UPLOADED

    @property
    def public_url(self) -> str | None:
        """Get the public URL for the uploaded image."""
        if self.variants and isinstance(self.variants, list):
            for variant in self.variants:
                if "public" in variant:
                    return variant
        return None

    @property
    def thumbnail_url(self) -> str | None:
        """Get the thumbnail URL for the uploaded image."""
        if self.variants and isinstance(self.variants, list):
            for variant in self.variants:
                if "thumbnail" in variant:
                    return variant
        return None

    @property
    def is_ready(self) -> bool:
        """Check if the image is ready for use (uploaded and processed)."""
        return self.status == ImageUploadStatus.UPLOADED and bool(self.variants)

    def get_url(self, variant: str = "public") -> str | None:
        """
        Get the URL for a specific variant of the image.

        Args:
            variant: The variant name (e.g., 'public', 'thumbnail', 'avatar')

        Returns:
            The URL for the specified variant, or None if not found
        """
        if not self.is_uploaded or not self.variants:
            return None

        if isinstance(self.variants, list):
            # Handle list format variants
            for variant_url in self.variants:
                if variant in variant_url:
                    return variant_url
        elif isinstance(self.variants, dict):
            # Handle dict format variants
            return self.variants.get(variant)

        return None

    def get_signed_url(self, variant: str = "public", expiry: int = 3600) -> str | None:
        """
        Get a signed URL for a specific variant of the image.

        Args:
            variant: The variant name (e.g., 'public', 'thumbnail', 'avatar')
            expiry: Expiry time in seconds (default: 3600 = 1 hour)

        Returns:
            A signed URL for the specified variant, or None if not available

        Note:
            This method requires the image to have require_signed_urls=True
            and proper Cloudflare API integration for signing URLs.
        """
        if not self.is_uploaded or not self.require_signed_urls:
            return self.get_url(variant)

        # For now, return the regular URL as signed URL generation
        # requires additional Cloudflare API integration
        # TODO: Implement actual signed URL generation via Cloudflare API
        return self.get_url(variant)

    def update_from_cloudflare_response(self, response_data: dict[str, Any]) -> None:
        """Update model fields from Cloudflare API response."""
        if "uploaded" in response_data:
            self.uploaded_at = timezone.now()
            self.status = ImageUploadStatus.UPLOADED

        if "draft" in response_data and response_data["draft"]:
            self.status = ImageUploadStatus.DRAFT

        if "variants" in response_data:
            self.variants = response_data["variants"]

        if "metadata" in response_data:
            self.cloudflare_metadata = response_data["metadata"]

        # Update image dimensions and format if available
        if "width" in response_data:
            self.width = response_data["width"]

        if "height" in response_data:
            self.height = response_data["height"]

        if "format" in response_data:
            self.format = response_data["format"]

        self.save()


class ImageUploadLog(models.Model):
    """Log model for tracking image upload events."""

    image = models.ForeignKey(
        CloudflareImage, on_delete=models.CASCADE, related_name="logs"
    )
    event_type = models.CharField(max_length=50)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cloudflare_image_logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["image", "timestamp"]),
            models.Index(fields=["event_type", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"ImageUploadLog({self.image.cloudflare_id}) - {self.event_type}"
