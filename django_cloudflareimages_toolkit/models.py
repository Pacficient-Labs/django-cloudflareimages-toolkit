"""
Django models for Cloudflare Images Toolkit.

This module contains the database models for tracking image uploads,
transformations, and their status throughout the upload process.
"""

import uuid
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.dateparse import parse_datetime

User = get_user_model()

# Max length of the indexed ``creator`` column. Kept at 255 so the index stays
# within InnoDB's key-length limit under MySQL/utf8mb4 (a 1024-char utf8mb4
# column needs 4096 bytes, over the 3072-byte cap). Cloudflare allows longer
# creator values; the service rejects over-length creators on upload and
# truncates longer values returned for externally-created images on register.
CREATOR_MAX_LENGTH = 255


class ImageUploadStatus(models.TextChoices):
    """Status choices for image uploads."""

    PENDING = "pending", "Pending"
    DRAFT = "draft", "Draft"
    UPLOADED = "uploaded", "Uploaded"
    FAILED = "failed", "Failed"
    EXPIRED = "expired", "Expired"


class CloudflareImageManager(models.Manager):
    """Manager exposing safe, first-class helpers for CloudflareImage."""

    def register_uploaded(
        self, cloudflare_id: str, user=None, expected_creator: str | None = None
    ) -> "CloudflareImage":
        """
        Safely register an already-uploaded image by its ``cloudflare_id``.

        Unlike ``get_or_create(cloudflare_id=...)`` with a client-supplied ID,
        this verifies the image against Cloudflare first: it confirms the image
        exists and that its draft state is cleared (bytes actually uploaded)
        before creating/returning the local record, then populates status,
        variants, and metadata from the Cloudflare response.

        Args:
            cloudflare_id: The Cloudflare image ID reported by the client.
            user: Django user to associate with the image (optional).
            expected_creator: If given, the Cloudflare ``creator`` on the image
                must equal this value (otherwise ``ImageOwnershipError`` is
                raised before any local row is created). Pass the uploader's id
                here when you set ``creator`` at upload time to enforce that a
                caller can only register their own image.

        Returns:
            The created or updated CloudflareImage instance.

        Raises:
            ImageNotFoundError: If the image does not exist in Cloudflare.
            ImageNotReadyError: If the image exists but is still a draft.
            ImageOwnershipError: If ``expected_creator`` does not match.
            CloudflareImagesError: For other Cloudflare API failures.
        """
        # Imported lazily to avoid a circular import (services imports models).
        from .services import cloudflare_service

        return cloudflare_service.register_uploaded_image(
            cloudflare_id, user=user, expected_creator=expected_creator
        )


class CloudflareImage(models.Model):
    """Model to track Cloudflare image uploads."""

    objects = CloudflareImageManager()

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
    # Cloudflare "creator" field: associates the image with a creator/user.
    # Indexed so records can be queried by creator from Django. See
    # CREATOR_MAX_LENGTH for why the length is capped.
    creator = models.CharField(max_length=CREATOR_MAX_LENGTH, blank=True, db_index=True)

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

    # The wall-clock at which this image was most recently confirmed referenced
    # by content. Maintained by the usage registry: bumped each time an
    # ``ImageUsage`` row is recorded for it. Null on legacy images that haven't
    # been touched by the registry. Drives orphan-retention cleanup so an image
    # that was referenced for years and just became unused isn't deleted on the
    # next run based on its (very old) ``created_at``.
    last_referenced_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "cloudflare_images"
        ordering = ["-created_at"]
        # Index names are pinned (and kept <=30 chars so they pass Django's
        # models.E034 check). Without explicit names, a newer Django's
        # makemigrations computes a different auto-name than the one baked into
        # migration 0001 and tries to write a spurious RenameIndex migration into
        # the installed package (site-packages). Migration 0006 renames the
        # original (auto-generated, over-long) 0001 index names to these.
        indexes = [
            models.Index(fields=["user", "status"], name="cfimg_user_status_idx"),
            models.Index(
                fields=["status", "created_at"], name="cfimg_status_created_idx"
            ),
            models.Index(fields=["expires_at"], name="cfimg_expires_idx"),
        ]

    def __str__(self) -> str:
        return f"CloudflareImage({self.cloudflare_id}) - {self.status}"

    @property
    def is_expired(self) -> bool:
        """Check if the upload URL has expired."""
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @property
    def is_uploaded(self) -> bool:
        """Check if the image has been successfully uploaded."""
        return self.status == ImageUploadStatus.UPLOADED

    @property
    def public_url(self) -> str | None:
        """Get the public variant URL for the uploaded image."""
        return self.get_variant_url("public")

    @property
    def thumbnail_url(self) -> str | None:
        """Get the thumbnail variant URL for the uploaded image."""
        return self.get_variant_url("thumbnail")

    def get_variant_url(self, variant_name: str) -> str | None:
        """
        Get the URL for a specific variant by name.

        Cloudflare returns variants as full URLs like:
        https://imagedelivery.net/<hash>/<id>/<variant_name>

        Args:
            variant_name: The variant name to look for (e.g., 'public', 'thumbnail')

        Returns:
            The full variant URL if found, None otherwise
        """
        if not self.variants:
            return None

        from .url_factory import image_url_factory

        found: str | None = None
        if isinstance(self.variants, list):
            # Variants are full URLs - find one ending with the variant name
            for variant_url in self.variants:
                if variant_url.rstrip("/").endswith(f"/{variant_name}"):
                    found = variant_url
                    break
            else:
                # Fallback: check if variant name appears anywhere in URL
                for variant_url in self.variants:
                    if variant_name in variant_url:
                        found = variant_url
                        break
        elif isinstance(self.variants, dict):
            # Handle dict format if Cloudflare ever returns that
            found = self.variants.get(variant_name)

        if found is None:
            return None
        # Honor a configured custom delivery domain (no-op when unconfigured).
        return image_url_factory.rewrite_url(found)

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
        if not self.is_uploaded:
            return None
        return self.get_variant_url(variant)

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
            # Prefer Cloudflare's own upload timestamp so registering or
            # re-syncing a previously uploaded image doesn't overwrite the real
            # time with "now" (which would corrupt uploaded_after/before filters).
            uploaded = response_data["uploaded"]
            if isinstance(uploaded, str):
                uploaded = parse_datetime(uploaded)
            self.uploaded_at = uploaded or self.uploaded_at or timezone.now()
            self.status = ImageUploadStatus.UPLOADED

        if "draft" in response_data and response_data["draft"]:
            self.status = ImageUploadStatus.DRAFT

        if "variants" in response_data:
            self.variants = response_data["variants"]

        # Cloudflare returns image metadata under "meta"; webhook payloads in
        # this toolkit use "metadata". Accept either, preferring "metadata".
        if "metadata" in response_data:
            self.cloudflare_metadata = response_data["metadata"]
        elif "meta" in response_data:
            self.cloudflare_metadata = response_data["meta"]

        if response_data.get("creator"):
            # Images created outside this toolkit may carry a creator longer
            # than our indexed column; truncate so the save can't fail and leave
            # the image untracked. Ownership checks compare the full CF value.
            self.creator = response_data["creator"][:CREATOR_MAX_LENGTH]

        if response_data.get("filename"):
            self.filename = response_data["filename"]

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
        # Names pinned and renamed by migration 0006 (see CloudflareImage.Meta).
        indexes = [
            models.Index(fields=["image", "timestamp"], name="cfimg_log_image_ts_idx"),
            models.Index(
                fields=["event_type", "timestamp"], name="cfimg_log_event_ts_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"ImageUploadLog({self.image.cloudflare_id}) - {self.event_type}"


class ImageUsage(models.Model):
    """Reverse index: which content object references which Cloudflare image.

    This is the missing half of the toolkit's source of truth. ``CloudflareImage``
    records *what* has been uploaded; ``ImageUsage`` records *where each image is
    used* — the model instance and field that point at a given ``cloudflare_id``.

    It is a *derived* index, not an independent source of truth: it is maintained
    automatically by signals on host models (see ``registry``/``signals``) and can
    always be rebuilt from those models with the ``reconcile_image_usage``
    management command.

    Two reverse-lookup helpers fall out of the schema:

    * orphaned images — ``CloudflareImage.objects.filter(usages__isnull=True)``
      (uploaded but referenced by no content), and
    * unregistered references — ``ImageUsage.objects.filter(image__isnull=True)``
      (content points at an image the toolkit has no ``CloudflareImage`` row for).
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    # CharField so both integer and UUID primary keys are supported.
    object_id = models.CharField(max_length=255, db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # The host field that holds the reference ("avatar", "image", ...), or any
    # caller-supplied label for references recorded through the public registry
    # API. The ``source`` column below distinguishes those.
    field_name = models.CharField(max_length=255)
    # Origin marker that survives reconcile: ``"auto"`` for rows derived from a
    # discovered ``CloudflareImageField`` (which can be pruned when the field is
    # renamed/removed) and ``"manual"`` for rows recorded through
    # ``register_usage(...)``. Manual rows are never pruned by reconcile
    # regardless of their ``field_name``.
    SOURCE_AUTO = "auto"
    SOURCE_MANUAL = "manual"
    SOURCE_CHOICES = [(SOURCE_AUTO, "Auto"), (SOURCE_MANUAL, "Manual")]
    source = models.CharField(
        max_length=10, choices=SOURCE_CHOICES, default=SOURCE_AUTO, db_index=True
    )
    # Source of truth for the reference itself (mirrors the value on the host
    # field). Retained even when no CloudflareImage row exists yet.
    cloudflare_id = models.CharField(max_length=255, db_index=True)
    # Resolved CloudflareImage when one exists; null marks an unregistered
    # reference. SET_NULL keeps the usage row (and its cloudflare_id) if the
    # image record is later deleted.
    image = models.ForeignKey(
        CloudflareImage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usages",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cloudflare_image_usages"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "field_name"],
                name="uniq_image_usage_per_field",
            )
        ]
        # Names pinned and renamed by migration 0006 (see CloudflareImage.Meta).
        indexes = [
            models.Index(
                fields=["content_type", "object_id"], name="cfimg_usage_ct_obj_idx"
            ),
            models.Index(fields=["cloudflare_id"], name="cfimg_usage_cfid_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"ImageUsage({self.cloudflare_id} -> "
            f"{self.content_type}:{self.object_id}.{self.field_name})"
        )

    @property
    def is_unregistered(self) -> bool:
        """True when the referenced image has no CloudflareImage record."""
        return self.image_id is None
