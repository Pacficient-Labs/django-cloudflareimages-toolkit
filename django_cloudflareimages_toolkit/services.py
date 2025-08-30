"""
Service layer for Cloudflare Images Toolkit.

This module contains the business logic for interacting with the
Cloudflare Images API, managing image uploads, and transformations.
"""

import logging
from datetime import timedelta
from typing import Any

import requests
from django.utils import timezone

from .models import CloudflareImage, ImageUploadLog, ImageUploadStatus
from .settings import cloudflare_settings

logger = logging.getLogger(__name__)


class CloudflareImagesError(Exception):
    """Base exception for Cloudflare Images operations."""

    pass


class CloudflareImagesService:
    """Service class for Cloudflare Images API operations."""

    def __init__(self):
        self.account_id = cloudflare_settings.account_id
        self.api_token = cloudflare_settings.api_token
        self.base_url = cloudflare_settings.base_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            }
        )

    def create_direct_upload_url(
        self,
        user=None,
        custom_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        require_signed_urls: bool | None = None,
        expiry_minutes: int | None = None,
    ) -> CloudflareImage:
        """
        Create a one-time upload URL for direct creator upload.

        Args:
            user: Django user instance (optional)
            custom_id: Custom ID for the image (optional)
            metadata: Additional metadata to store with the image
            require_signed_urls: Whether to require signed URLs
            expiry_minutes: Minutes until the upload URL expires

        Returns:
            CloudflareImage instance with upload URL

        Raises:
            CloudflareImagesError: If the API request fails
        """
        if require_signed_urls is None:
            require_signed_urls = cloudflare_settings.require_signed_urls

        if expiry_minutes is None:
            expiry_minutes = cloudflare_settings.default_expiry_minutes

        if metadata is None:
            metadata = {}

        # Calculate expiry time
        expires_at = timezone.now() + timedelta(minutes=expiry_minutes)

        # Prepare request data
        form_data = {
            "requireSignedURLs": str(require_signed_urls).lower(),
            "metadata": metadata,
        }

        if custom_id:
            form_data["id"] = custom_id

        # Make API request
        url = f"{self.base_url}/accounts/{self.account_id}/images/v2/direct_upload"

        try:
            # Use form data for this endpoint
            self.session.headers.pop("Content-Type", None)
            response = self.session.post(url, data=form_data)
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

        finally:
            # Restore Content-Type header
            self.session.headers["Content-Type"] = "application/json"

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
            response = self.session.get(url)
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
            response = self.session.delete(url)
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
