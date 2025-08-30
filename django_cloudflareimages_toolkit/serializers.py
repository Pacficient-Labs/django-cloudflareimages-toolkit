"""
Serializers for Cloudflare Images Direct Creator Upload.

This module contains the DRF serializers for API endpoints.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import CloudflareImage, ImageUploadLog, ImageUploadStatus

User = get_user_model()


class ImageUploadRequestSerializer(serializers.Serializer):
    """Serializer for requesting a direct upload URL."""

    custom_id = serializers.CharField(
        max_length=255, required=False, help_text="Custom ID for the image (optional)"
    )
    metadata = serializers.JSONField(
        required=False,
        default=dict,
        help_text="Additional metadata to store with the image",
    )
    require_signed_urls = serializers.BooleanField(
        required=False,
        help_text="Whether to require signed URLs for accessing the image",
    )
    expiry_minutes = serializers.IntegerField(
        required=False,
        min_value=2,
        max_value=360,
        help_text="Minutes until the upload URL expires (2-360 minutes)",
    )
    filename = serializers.CharField(
        max_length=255, required=False, help_text="Original filename for reference"
    )

    def validate_custom_id(self, value: str) -> str:
        """Validate custom ID format."""
        if value and CloudflareImage.objects.filter(cloudflare_id=value).exists():
            raise serializers.ValidationError(
                "An image with this custom ID already exists."
            )
        return value


class CloudflareImageSerializer(serializers.ModelSerializer):
    """Serializer for CloudflareImage model."""

    public_url = serializers.ReadOnlyField()
    thumbnail_url = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    is_uploaded = serializers.ReadOnlyField()

    class Meta:
        model = CloudflareImage
        fields = [
            "id",
            "cloudflare_id",
            "filename",
            "original_filename",
            "content_type",
            "file_size",
            "upload_url",
            "status",
            "require_signed_urls",
            "metadata",
            "created_at",
            "updated_at",
            "uploaded_at",
            "expires_at",
            "variants",
            "cloudflare_metadata",
            "public_url",
            "thumbnail_url",
            "is_expired",
            "is_uploaded",
        ]
        read_only_fields = [
            "id",
            "cloudflare_id",
            "upload_url",
            "status",
            "created_at",
            "updated_at",
            "uploaded_at",
            "expires_at",
            "variants",
            "cloudflare_metadata",
        ]


class ImageUploadResponseSerializer(serializers.Serializer):
    """Serializer for upload URL response."""

    id = serializers.UUIDField(help_text="Internal image ID")
    cloudflare_id = serializers.CharField(help_text="Cloudflare image ID")
    upload_url = serializers.URLField(help_text="One-time upload URL")
    expires_at = serializers.DateTimeField(help_text="Upload URL expiration time")
    status = serializers.CharField(help_text="Current upload status")


class ImageStatusSerializer(serializers.Serializer):
    """Serializer for image status response."""

    id = serializers.UUIDField()
    cloudflare_id = serializers.CharField()
    status = serializers.CharField()
    uploaded_at = serializers.DateTimeField(allow_null=True)
    variants = serializers.ListField(child=serializers.URLField(), required=False)
    public_url = serializers.URLField(allow_null=True)
    thumbnail_url = serializers.URLField(allow_null=True)
    is_uploaded = serializers.BooleanField()
    is_expired = serializers.BooleanField()


class ImageUploadLogSerializer(serializers.ModelSerializer):
    """Serializer for ImageUploadLog model."""

    class Meta:
        model = ImageUploadLog
        fields = ["id", "event_type", "message", "data", "timestamp"]
        read_only_fields = ["id", "timestamp"]


class WebhookPayloadSerializer(serializers.Serializer):
    """Serializer for validating webhook payloads."""

    id = serializers.CharField(help_text="Cloudflare image ID")
    uploaded = serializers.DateTimeField(required=False)
    draft = serializers.BooleanField(required=False)
    variants = serializers.ListField(child=serializers.URLField(), required=False)
    metadata = serializers.JSONField(required=False)
    requireSignedURLs = serializers.BooleanField(required=False)


class BulkImageStatusSerializer(serializers.Serializer):
    """Serializer for bulk image status requests."""

    image_ids = serializers.ListField(
        child=serializers.UUIDField(),
        max_length=50,
        help_text="List of image IDs to check (max 50)",
    )


class ImageFilterSerializer(serializers.Serializer):
    """Serializer for filtering images."""

    status = serializers.ChoiceField(
        choices=ImageUploadStatus.choices,
        required=False,
        help_text="Filter by upload status",
    )
    uploaded_after = serializers.DateTimeField(
        required=False, help_text="Filter images uploaded after this date"
    )
    uploaded_before = serializers.DateTimeField(
        required=False, help_text="Filter images uploaded before this date"
    )
    has_variants = serializers.BooleanField(
        required=False, help_text="Filter images that have variants"
    )
    require_signed_urls = serializers.BooleanField(
        required=False, help_text="Filter by signed URL requirement"
    )
