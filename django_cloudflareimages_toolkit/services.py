"""
Service layer for Cloudflare Images Toolkit.

This module contains the business logic for interacting with the
Cloudflare Images API, managing image uploads, and transformations.
"""

import json
import logging
from datetime import timedelta
from typing import Any

import requests
from django.utils import timezone

from .exceptions import (
    CloudflareImagesError,
)
from .models import CloudflareImage, ImageUploadLog, ImageUploadStatus
from .settings import cloudflare_settings

logger = logging.getLogger(__name__)


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

    def get_direct_upload_url(
        self,
        user=None,
        custom_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        require_signed_urls: bool | None = None,
        expiry_minutes: int | None = None,
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
        )
        return {"id": image.cloudflare_id, "uploadURL": image.upload_url}

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
            "metadata": json.dumps(metadata),
        }

        if custom_id:
            form_data["id"] = custom_id

        # Make API request
        url = f"{self.base_url}/accounts/{self.account_id}/images/v2/direct_upload"

        try:
            # Use form data for this endpoint
            self.session.headers.pop("Content-Type", None)
            response = self.session.post(url, files=form_data)
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

    def list_images(self, page: int = 1, per_page: int = 50) -> dict[str, Any]:
        """
        List images from Cloudflare Images.

        Args:
            page: Page number for pagination (default: 1)
            per_page: Number of images per page (default: 50, max: 100)

        Returns:
            Dictionary with pagination info and list of images

        Raises:
            CloudflareImagesError: If the API request fails
        """
        url = f"{self.base_url}/accounts/{self.account_id}/images/v1"
        params = {
            "page": page,
            "per_page": min(per_page, 100),  # Cloudflare max is 100
        }

        try:
            response = self.session.get(url, params=params)
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

            logger.info(f"Retrieved image details for {image_id}")
            return data

        except requests.RequestException as e:
            logger.error(f"Failed to get image {image_id}: {str(e)}")
            raise CloudflareImagesError(f"Failed to get image: {str(e)}") from e

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
            response = self.session.patch(url, json=update_data)
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
