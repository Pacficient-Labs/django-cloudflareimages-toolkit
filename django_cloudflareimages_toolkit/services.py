"""
Service layer for Cloudflare Images Toolkit.

This module contains the business logic for interacting with the
Cloudflare Images API, managing image uploads, and transformations.
"""

import json
import logging
import threading
from datetime import timedelta
from typing import Any

import requests
from django.utils import timezone

from .exceptions import (
    CloudflareImagesError,
    ImageNotFoundError,
    ImageNotReadyError,
    ImageOwnershipError,
)
from .models import (
    CREATOR_MAX_LENGTH,
    CloudflareImage,
    ImageUploadLog,
    ImageUploadStatus,
)
from .settings import cloudflare_settings

logger = logging.getLogger(__name__)


class CloudflareImagesService:
    """Service class for Cloudflare Images API operations."""

    def __init__(self):
        # Each thread gets its own Session so there is no shared mutable state
        # (e.g. cookies, adapters) between concurrent callers.
        self._local: threading.local = threading.local()

    @property
    def account_id(self) -> str:
        return cloudflare_settings.account_id

    @property
    def api_token(self) -> str:
        return cloudflare_settings.api_token

    @property
    def base_url(self) -> str:
        return cloudflare_settings.base_url

    @property
    def session(self) -> requests.Session:
        # Return the Session for the current thread, creating it on first use.
        # Using threading.local() means each thread has its own independent
        # Session so concurrent API calls cannot share cookies or other mutable
        # session state. Auth headers are passed per-request via _auth_headers()
        # so override_settings changes are reflected immediately.
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
        return self._local.session

    def _auth_headers(self) -> dict[str, str]:
        """Return per-request Authorization headers using the current API token.

        Reading the token on each call keeps the header in sync with
        override_settings changes and avoids mutating shared session state.
        """
        return {"Authorization": f"Bearer {self.api_token}"}

    def get_direct_upload_url(
        self,
        user=None,
        custom_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        require_signed_urls: bool | None = None,
        expiry_minutes: int | None = None,
        creator: str | None = None,
    ) -> dict[str, str]:
        """
        Get a one-time upload URL for direct creator upload.

        This is an alias for create_direct_upload_url that returns a dict
        to match the documentation examples.
        """
        image = self.create_direct_upload_url(
            user=user,
            custom_id=custom_id,
            metadata=metadata,
            require_signed_urls=require_signed_urls,
            expiry_minutes=expiry_minutes,
            creator=creator,
        )
        return {"id": image.cloudflare_id, "uploadURL": image.upload_url}

    def create_direct_upload_url(
        self,
        user=None,
        custom_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        require_signed_urls: bool | None = None,
        expiry_minutes: int | None = None,
        creator: str | None = None,
    ) -> CloudflareImage:
        """
        Create a one-time upload URL for direct creator upload.

        Settings-backed defaults are applied for any argument left as ``None``:
        ``require_signed_urls`` and ``expiry_minutes`` from their respective
        settings, ``creator`` from ``DEFAULT_CREATOR``, and ``metadata`` is
        merged on top of ``DEFAULT_METADATA`` (per-request keys win).

        Args:
            user: Django user instance (optional)
            custom_id: Custom ID for the image (optional)
            metadata: Additional metadata to store with the image
            require_signed_urls: Whether to require signed URLs
            expiry_minutes: Minutes until the upload URL expires
            creator: Cloudflare ``creator`` value to associate with the image

        Returns:
            CloudflareImage instance with upload URL

        Raises:
            CloudflareImagesError: If the API request fails
        """
        if require_signed_urls is None:
            require_signed_urls = cloudflare_settings.require_signed_urls

        if expiry_minutes is None:
            expiry_minutes = cloudflare_settings.default_expiry_minutes

        # Guard against non-dict metadata (e.g. a JSON array from a direct
        # caller) before the spread-merge below, which would otherwise raise a
        # bare TypeError. The view maps CloudflareImagesError to a 400.
        if metadata is not None and not isinstance(metadata, dict):
            raise CloudflareImagesError("metadata must be a dict")

        # Merge per-request metadata on top of the configured defaults so that
        # per-request keys take precedence over DEFAULT_METADATA.
        metadata = {**cloudflare_settings.default_metadata, **(metadata or {})}

        if creator is None:
            creator = cloudflare_settings.default_creator

        # Reject an over-length creator before the Cloudflare request so we never
        # complete an upload we can't persist locally (the column caps at 255).
        if creator and len(creator) > CREATOR_MAX_LENGTH:
            raise CloudflareImagesError(
                f"creator exceeds {CREATOR_MAX_LENGTH} characters"
            )

        # Give a configured metadata factory the final say. As trusted
        # server-side code it may augment or override the resolved metadata.
        # Precedence: DEFAULT_METADATA < per-request metadata < factory output.
        factory = cloudflare_settings.get_metadata_factory()
        if factory is not None:
            metadata = factory(
                metadata=metadata,
                user=user,
                custom_id=custom_id,
                creator=creator,
            )
            if not isinstance(metadata, dict):
                raise CloudflareImagesError(
                    "METADATA_FACTORY must return a dict of metadata"
                )

        # Calculate expiry time (must be 2 min to 6 hours in the future per API docs)
        expiry_minutes = max(2, min(expiry_minutes, 360))
        expires_at = timezone.now() + timedelta(minutes=expiry_minutes)

        # Prepare request data
        form_data = {
            "requireSignedURLs": str(require_signed_urls).lower(),
            "metadata": json.dumps(metadata),
            "expiry": expires_at.isoformat(),
        }

        if custom_id:
            form_data["id"] = custom_id

        if creator:
            form_data["creator"] = creator

        # Make API request
        url = f"{self.base_url}/accounts/{self.account_id}/images/v2/direct_upload"

        try:
            # This endpoint requires multipart/form-data. Using (None, value) tuples
            # encodes each field as a plain form field (no filename) so the request
            # matches Cloudflare's expected -F key=value semantics.
            files = {k: (None, v) for k, v in form_data.items()}
            response = self.session.post(url, files=files, headers=self._auth_headers())
            response.raise_for_status()

            data = response.json()

            if not data.get("success"):
                error_msg = ", ".join(
                    [
                        err.get("message", "Unknown error")
                        for err in data.get("errors", [])
                    ]
                )
                raise CloudflareImagesError(f"Cloudflare API error: {error_msg}")

            result = data["result"]

            # Create CloudflareImage record
            image = CloudflareImage.objects.create(
                cloudflare_id=result["id"],
                user=user,
                upload_url=result["uploadURL"],
                status=ImageUploadStatus.PENDING,
                require_signed_urls=require_signed_urls,
                metadata=metadata,
                creator=creator or "",
                expires_at=expires_at,
            )

            # Log the creation
            ImageUploadLog.objects.create(
                image=image,
                event_type="upload_url_created",
                message="Direct upload URL created successfully",
                data={"response": result},
            )

            logger.info(f"Created direct upload URL for image {image.cloudflare_id}")
            return image

        except requests.RequestException as e:
            logger.error(f"Failed to create direct upload URL: {str(e)}")
            raise CloudflareImagesError(f"Failed to create upload URL: {str(e)}") from e

    def check_image_status(self, image: CloudflareImage) -> dict[str, Any]:
        """
        Check the status of an image upload.

        Args:
            image: CloudflareImage instance

        Returns:
            Dictionary containing the image status data

        Raises:
            CloudflareImagesError: If the API request fails
        """
        url = f"{self.base_url}/accounts/{self.account_id}/images/v1/{image.cloudflare_id}"

        try:
            response = self.session.get(url, headers=self._auth_headers())
            response.raise_for_status()

            data = response.json()

            if not data.get("success"):
                error_msg = ", ".join(
                    [
                        err.get("message", "Unknown error")
                        for err in data.get("errors", [])
                    ]
                )
                raise CloudflareImagesError(f"Cloudflare API error: {error_msg}")

            result = data["result"]

            # Update the image record
            image.update_from_cloudflare_response(result)

            # Log the status check
            ImageUploadLog.objects.create(
                image=image,
                event_type="status_checked",
                message=f"Image status checked: {image.status}",
                data={"response": result},
            )

            logger.info(
                f"Checked status for image {image.cloudflare_id}: {image.status}"
            )
            return result

        except requests.RequestException as e:
            logger.error(
                f"Failed to check image status for {image.cloudflare_id}: {str(e)}"
            )
            raise CloudflareImagesError(
                f"Failed to check image status: {str(e)}"
            ) from e

    def list_images(self, page: int = 1, per_page: int = 1000) -> dict[str, Any]:
        """
        List images from Cloudflare Images.

        Args:
            page: Page number for pagination (default: 1)
            per_page: Number of images per page (default: 1000, max: 10000)

        Returns:
            Dictionary with pagination info and list of images

        Raises:
            CloudflareImagesError: If the API request fails
        """
        url = f"{self.base_url}/accounts/{self.account_id}/images/v1"
        params = {
            "page": page,
            "per_page": min(per_page, 10000),  # Cloudflare max is 10000
        }

        try:
            response = self.session.get(
                url, params=params, headers=self._auth_headers()
            )
            response.raise_for_status()

            data = response.json()

            if not data.get("success"):
                error_msg = ", ".join(
                    [
                        err.get("message", "Unknown error")
                        for err in data.get("errors", [])
                    ]
                )
                raise CloudflareImagesError(f"Cloudflare API error: {error_msg}")

            logger.info(f"Listed images: page {page}, per_page {per_page}")
            return data

        except requests.RequestException as e:
            logger.error(f"Failed to list images: {str(e)}")
            raise CloudflareImagesError(f"Failed to list images: {str(e)}") from e

    def get_image(self, image_id: str) -> dict[str, Any]:
        """
        Get details for a specific image.

        Args:
            image_id: Cloudflare image ID

        Returns:
            Dictionary with image details

        Raises:
            CloudflareImagesError: If the API request fails
        """
        url = f"{self.base_url}/accounts/{self.account_id}/images/v1/{image_id}"

        try:
            response = self.session.get(url, headers=self._auth_headers())
            response.raise_for_status()

            data = response.json()

            if not data.get("success"):
                error_msg = ", ".join(
                    [
                        err.get("message", "Unknown error")
                        for err in data.get("errors", [])
                    ]
                )
                raise CloudflareImagesError(f"Cloudflare API error: {error_msg}")

            logger.info(f"Retrieved image details for {image_id}")
            return data

        except requests.RequestException as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code == 404:
                # A missing image is a distinct, typed error so callers can
                # react to it specifically. ImageNotFoundError subclasses
                # CloudflareImagesError, so existing ``except`` blocks still match.
                logger.warning(f"Image {image_id} not found in Cloudflare")
                raise ImageNotFoundError(
                    f"Image {image_id} not found in Cloudflare",
                    status_code=404,
                ) from e
            logger.error(f"Failed to get image {image_id}: {str(e)}")
            raise CloudflareImagesError(f"Failed to get image: {str(e)}") from e

    def register_uploaded_image(
        self, cloudflare_id: str, user=None, expected_creator: str | None = None
    ) -> CloudflareImage:
        """
        Verify an uploaded image against Cloudflare and persist it locally.

        This is the safe alternative to ``CloudflareImage.objects.get_or_create(
        cloudflare_id=<client-supplied id>)``: it fetches the image details from
        Cloudflare, confirms the image exists and that its draft state is
        cleared (bytes were actually uploaded), and only then creates/returns
        the local record with status, variants, and metadata populated from the
        Cloudflare response.

        Args:
            cloudflare_id: The Cloudflare image ID reported by the client.
            user: Django user to associate with the image (optional).
            expected_creator: If given, the Cloudflare ``creator`` on the image
                must equal this value or ``ImageOwnershipError`` is raised before
                any local row is created. Use it (e.g. with the uploader's id)
                to stop a caller registering another user's image by submitting
                an arbitrary id from the same Cloudflare account.

        Returns:
            The created or updated CloudflareImage instance.

        Raises:
            ImageNotFoundError: If the image does not exist in Cloudflare.
            ImageNotReadyError: If the image exists but is still a draft.
            ImageOwnershipError: If ``expected_creator`` does not match.
            CloudflareImagesError: For other Cloudflare API failures.
        """
        # Raises ImageNotFoundError if the image does not exist in Cloudflare.
        data = self.get_image(cloudflare_id)
        result = data["result"]

        # A draft image means the upload URL was created but no bytes have been
        # uploaded yet. Refuse to register it -- do not create a local row.
        if result.get("draft"):
            logger.warning(
                f"Refusing to register draft image {cloudflare_id}: upload incomplete"
            )
            raise ImageNotReadyError(
                f"Image {cloudflare_id} is still a draft (upload not completed)"
            )

        # Optional ownership gate: verify the Cloudflare creator matches the
        # expected owner BEFORE creating any local row, so a caller can't attach
        # someone else's completed image to themselves.
        if expected_creator is not None and result.get("creator") != expected_creator:
            logger.warning(
                f"Refusing to register image {cloudflare_id}: creator mismatch"
            )
            raise ImageOwnershipError(
                f"Image {cloudflare_id} does not belong to the expected creator"
            )

        # Cloudflare returns upload metadata under "meta" (older payloads use
        # "metadata"). For a registered-by-id image this is the only metadata we
        # have, so mirror it into the queryable ``metadata`` field too.
        cf_meta = result.get("meta") or result.get("metadata") or {}

        image, created = CloudflareImage.objects.get_or_create(
            cloudflare_id=cloudflare_id,
            defaults={
                "user": user,
                "upload_url": "",
                "status": ImageUploadStatus.UPLOADED,
                "require_signed_urls": result.get(
                    "requireSignedURLs", cloudflare_settings.require_signed_urls
                ),
                "metadata": cf_meta,
                # The upload URL has already been consumed; record "now" so the
                # required expires_at field is populated for registered images.
                "expires_at": timezone.now(),
            },
        )

        # Associate the user on pre-existing rows that don't have one yet.
        if user is not None and image.user_id is None:
            image.user = user

        # Backfill the queryable metadata field on a pre-existing row when CF
        # has metadata for it (don't clobber existing values with an empty dict).
        if not created and cf_meta:
            image.metadata = cf_meta

        # Populate status, variants, cloudflare_metadata, creator and filename.
        image.update_from_cloudflare_response(result)

        ImageUploadLog.objects.create(
            image=image,
            event_type="image_registered",
            message=(
                "Image registered from Cloudflare"
                if created
                else "Existing image refreshed during registration"
            ),
            data={"response": result},
        )

        logger.info(
            f"Registered uploaded image {image.cloudflare_id} (created={created})"
        )
        return image

    def update_image(
        self,
        image_id: str,
        metadata: dict[str, Any] | None = None,
        require_signed_urls: bool | None = None,
    ) -> dict[str, Any]:
        """
        Update image metadata and settings.

        Args:
            image_id: Cloudflare image ID
            metadata: New metadata for the image
            require_signed_urls: Whether to require signed URLs

        Returns:
            Dictionary with updated image details

        Raises:
            CloudflareImagesError: If the API request fails
        """
        url = f"{self.base_url}/accounts/{self.account_id}/images/v1/{image_id}"

        update_data = {}
        if metadata is not None:
            update_data["metadata"] = metadata
        if require_signed_urls is not None:
            update_data["requireSignedURLs"] = require_signed_urls

        try:
            response = self.session.patch(
                url, json=update_data, headers=self._auth_headers()
            )
            response.raise_for_status()

            data = response.json()

            if not data.get("success"):
                error_msg = ", ".join(
                    [
                        err.get("message", "Unknown error")
                        for err in data.get("errors", [])
                    ]
                )
                raise CloudflareImagesError(f"Cloudflare API error: {error_msg}")

            # Update local CloudflareImage if it exists
            try:
                image = CloudflareImage.objects.get(cloudflare_id=image_id)
                if metadata is not None:
                    image.metadata.update(metadata)
                if require_signed_urls is not None:
                    image.require_signed_urls = require_signed_urls
                image.save()
            except CloudflareImage.DoesNotExist:
                pass

            logger.info(f"Updated image {image_id}")
            return data

        except requests.RequestException as e:
            logger.error(f"Failed to update image {image_id}: {str(e)}")
            raise CloudflareImagesError(f"Failed to update image: {str(e)}") from e

    def delete_image(self, image: CloudflareImage) -> bool:
        """
        Delete an image from Cloudflare Images.

        Args:
            image: CloudflareImage instance

        Returns:
            True if deletion was successful

        Raises:
            CloudflareImagesError: If the API request fails
        """
        url = f"{self.base_url}/accounts/{self.account_id}/images/v1/{image.cloudflare_id}"

        try:
            response = self.session.delete(url, headers=self._auth_headers())
            response.raise_for_status()

            data = response.json()

            if not data.get("success"):
                error_msg = ", ".join(
                    [
                        err.get("message", "Unknown error")
                        for err in data.get("errors", [])
                    ]
                )
                raise CloudflareImagesError(f"Cloudflare API error: {error_msg}")

            # Log the deletion
            ImageUploadLog.objects.create(
                image=image,
                event_type="image_deleted",
                message="Image deleted from Cloudflare",
                data={"response": data},
            )

            logger.info(f"Deleted image {image.cloudflare_id}")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to delete image {image.cloudflare_id}: {str(e)}")
            raise CloudflareImagesError(f"Failed to delete image: {str(e)}") from e

    def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Validate webhook signature from Cloudflare.

        Args:
            payload: Raw webhook payload
            signature: Signature from webhook headers (should be in format 'sha256=...')

        Returns:
            True if signature is valid
        """
        if not cloudflare_settings.webhook_secret:
            logger.warning(
                "Webhook secret not configured, skipping signature validation"
            )
            return True

        import hashlib
        import hmac

        # Remove 'sha256=' prefix if present
        if signature.startswith("sha256="):
            signature = signature[7:]

        expected_signature = hmac.new(
            cloudflare_settings.webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected_signature)

    def process_webhook(self, payload: dict[str, Any]) -> CloudflareImage | None:
        """
        Process webhook payload from Cloudflare.

        Args:
            payload: Webhook payload data

        Returns:
            Updated CloudflareImage instance if found
        """
        try:
            image_id = payload.get("id")
            if not image_id:
                logger.warning("Webhook payload missing image ID")
                return None

            try:
                image = CloudflareImage.objects.get(cloudflare_id=image_id)
            except CloudflareImage.DoesNotExist:
                logger.warning(f"Received webhook for unknown image: {image_id}")
                return None

            # Update image from webhook data
            image.update_from_cloudflare_response(payload)

            # Log the webhook
            ImageUploadLog.objects.create(
                image=image,
                event_type="webhook_received",
                message="Webhook processed successfully",
                data={"payload": payload},
            )

            logger.info(f"Processed webhook for image {image.cloudflare_id}")
            return image

        except Exception as e:
            logger.error(f"Failed to process webhook: {str(e)}")
            return None


# Global service instance
cloudflare_service = CloudflareImagesService()
