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
