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

from .constants import (
    MAX_EXPIRY_MINUTES,
    MAX_LIST_PER_PAGE,
    MIN_EXPIRY_MINUTES,
)
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

    def _request(
        self,
        method: str,
        url: str,
        *,
        error_prefix: str,
        not_found_message: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Perform a Cloudflare API call and return the parsed JSON envelope.

        Centralizes the request/response scaffolding that every public method
        otherwise repeats:

          * injects the per-request ``Authorization`` header,
          * raises for HTTP status,
          * parses the JSON body,
          * enforces Cloudflare's ``success``/``errors`` envelope (joining the
            returned error messages), and
          * maps a ``requests.RequestException`` to ``CloudflareImagesError``.

        Each public method then reduces to request-shaping plus handling of the
        parsed result, so a change to error context, retries, or timeouts is
        made here once instead of in ~6 copies.

        Args:
            method: ``requests.Session`` method name (``"get"``, ``"post"``,
                ``"patch"``, ``"delete"`` ...).
            url: Fully-qualified Cloudflare endpoint.
            error_prefix: Human prefix for the raised/logged error
                (e.g. ``"Failed to get image"``).
            not_found_message: When provided, an HTTP ``404`` is surfaced as the
                typed :class:`ImageNotFoundError` (carrying this message) instead
                of a generic error, preserving the 404 specialization used by
                ``get_image`` and ``delete_image``. When ``None`` a 404 is
                treated like any other request failure.
            **kwargs: Forwarded to the session call (``params``, ``json``,
                ``files`` ...). Any ``headers`` are merged on top of the auth
                header.

        Returns:
            The decoded JSON ``dict`` (the full envelope, including ``result``).

        Raises:
            ImageNotFoundError: HTTP 404 when ``not_found_message`` is set.
            CloudflareImagesError: Any other transport/HTTP failure, or a
                ``success: false`` envelope.
        """
        headers = {**self._auth_headers(), **kwargs.pop("headers", {})}
        try:
            response = getattr(self.session, method)(url, headers=headers, **kwargs)
            response.raise_for_status()
        except requests.RequestException as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if not_found_message is not None and status_code == 404:
                # A missing image is a distinct, typed error so callers can react
                # to it specifically. ImageNotFoundError subclasses
                # CloudflareImagesError, so existing ``except`` blocks still match.
                logger.warning(not_found_message)
                raise ImageNotFoundError(not_found_message, status_code=404) from e
            logger.error(f"{error_prefix}: {str(e)}")
            raise CloudflareImagesError(f"{error_prefix}: {str(e)}") from e

        data = response.json()
        if not data.get("success"):
            error_msg = ", ".join(
                err.get("message", "Unknown error") for err in data.get("errors", [])
            )
            raise CloudflareImagesError(f"Cloudflare API error: {error_msg}")
        return data

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

        # Calculate expiry time (must be 2 min to 6 hours in the future per API
        # docs); clamp to the shared Cloudflare bounds.
        expiry_minutes = max(
            MIN_EXPIRY_MINUTES, min(expiry_minutes, MAX_EXPIRY_MINUTES)
        )
        expires_at = timezone.now() + timedelta(minutes=expiry_minutes)

        # Prepare request data. ``sort_keys=True`` makes the serialized metadata
        # deterministic: identical metadata always produces a byte-identical
        # request body regardless of dict insertion order, which keeps the
        # outgoing request reproducible and easy to assert on.
        form_data = {
            "requireSignedURLs": str(require_signed_urls).lower(),
            "metadata": json.dumps(metadata, sort_keys=True),
            "expiry": expires_at.isoformat(),
        }

        if custom_id:
            form_data["id"] = custom_id

        if creator:
            form_data["creator"] = creator

        # Make API request
        url = f"{self.base_url}/accounts/{self.account_id}/images/v2/direct_upload"

        # This endpoint requires multipart/form-data. Using (None, value) tuples
        # encodes each field as a plain form field (no filename) so the request
        # matches Cloudflare's expected -F key=value semantics.
        files = {k: (None, v) for k, v in form_data.items()}
        data = self._request(
            "post", url, error_prefix="Failed to create upload URL", files=files
        )

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

        data = self._request("get", url, error_prefix="Failed to check image status")
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

        logger.info(f"Checked status for image {image.cloudflare_id}: {image.status}")
        return result

    def list_images(self, page: int = 1, per_page: int = 1000) -> dict[str, Any]:
        """
        List images from Cloudflare Images.

        Args:
            page: Page number for pagination (default: 1)
            per_page: Number of images per page (default: 1000; clamped to the
                Cloudflare maximum, ``MAX_LIST_PER_PAGE``)

        Returns:
            Dictionary with pagination info and list of images

        Raises:
            CloudflareImagesError: If the API request fails
        """
        url = f"{self.base_url}/accounts/{self.account_id}/images/v1"
        params = {
            "page": page,
            "per_page": min(per_page, MAX_LIST_PER_PAGE),  # Cloudflare max
        }

        data = self._request(
            "get", url, error_prefix="Failed to list images", params=params
        )
        logger.info(f"Listed images: page {page}, per_page {per_page}")
        return data

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

        # A 404 is surfaced as the typed ImageNotFoundError (see _request) so
        # callers like register_uploaded_image can react to a missing image.
        data = self._request(
            "get",
            url,
            error_prefix="Failed to get image",
            not_found_message=f"Image {image_id} not found in Cloudflare",
        )
        logger.info(f"Retrieved image details for {image_id}")
        return data

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
        # Reject an id we couldn't store before doing any remote work, so an
        # externally-created custom id longer than the column raises the typed
        # failure (and creates no row) rather than a database error on save.
        max_id_len = CloudflareImage._meta.get_field("cloudflare_id").max_length
        if len(cloudflare_id) > max_id_len:
            raise CloudflareImagesError(
                f"cloudflare_id exceeds {max_id_len} characters"
            )

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
        elif (
            user is not None and image.user_id is not None and image.user_id != user.pk
        ):
            # The image is already tracked locally for a different user. Refuse
            # rather than returning another user's record to this caller.
            logger.warning(
                f"Refusing to register image {cloudflare_id}: owned by another user"
            )
            raise ImageOwnershipError(
                f"Image {cloudflare_id} is already registered to another user"
            )

        # Backfill the queryable metadata field on a pre-existing row when CF
        # has metadata for it (don't clobber existing values with an empty dict).
        if not created and cf_meta:
            image.metadata = cf_meta

        # Refresh the signed-URL flag from Cloudflare on a pre-existing row too
        # (get_or_create ignores ``defaults`` when the row already exists, and
        # update_from_cloudflare_response does not carry requireSignedURLs).
        if not created and "requireSignedURLs" in result:
            image.require_signed_urls = result["requireSignedURLs"]

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

        data = self._request(
            "patch", url, error_prefix="Failed to update image", json=update_data
        )

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

    def delete_image(self, image: CloudflareImage, *, missing_ok: bool = False) -> bool:
        """
        Delete an image from Cloudflare Images.

        A Cloudflare ``404`` (the image is already absent) is surfaced as the
        typed :class:`ImageNotFoundError`, mirroring :meth:`get_image`. Because
        ``ImageNotFoundError`` subclasses ``CloudflareImagesError``, existing
        ``except CloudflareImagesError`` callers keep matching it.

        Args:
            image: CloudflareImage instance
            missing_ok: When ``True``, a Cloudflare ``404`` (image already gone)
                is treated as a *successful* delete and returns ``True`` instead
                of raising. The desired end state for a delete is "not in
                Cloudflare", so callers whose job is to converge on that state
                (orphan cleanup, the admin delete action, the viewset delete)
                pass ``missing_ok=True`` and remain idempotent across repeated
                or partially-failed runs.

        Returns:
            True if deletion was successful (or the image was already absent and
            ``missing_ok`` is set).

        Raises:
            ImageNotFoundError: Cloudflare returned 404 and ``missing_ok`` is
                False.
            CloudflareImagesError: For any other API/transport failure.
        """
        url = f"{self.base_url}/accounts/{self.account_id}/images/v1/{image.cloudflare_id}"

        try:
            # _request surfaces a Cloudflare 404 as the typed ImageNotFoundError.
            data = self._request(
                "delete",
                url,
                error_prefix="Failed to delete image",
                not_found_message=f"Image {image.cloudflare_id} not found in Cloudflare",
            )
        except ImageNotFoundError:
            # The image is already gone in Cloudflare. For an idempotent caller
            # that is the desired end state, so report success and let it remove
            # the local row; otherwise re-raise the typed not-found error (still
            # a CloudflareImagesError subclass).
            if missing_ok:
                logger.info(
                    f"Image {image.cloudflare_id} already absent in Cloudflare; "
                    "treating delete as successful"
                )
                return True
            raise

        # Log the deletion
        ImageUploadLog.objects.create(
            image=image,
            event_type="image_deleted",
            message="Image deleted from Cloudflare",
            data={"response": data},
        )

        logger.info(f"Deleted image {image.cloudflare_id}")
        return True

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

        Returns the updated ``CloudflareImage`` when the payload matches a known
        image, or ``None`` only for the genuine *unknown image* case — a missing
        id or no matching local row. The caller (``WebhookView``) maps ``None``
        to a 404.

        Crucially, this does NOT swallow unexpected errors. A transient failure
        (e.g. a DB hiccup, or a save error inside
        ``update_from_cloudflare_response``) is allowed to propagate so the
        view's existing 500 path runs and Cloudflare retries delivery. The
        previous catch-all ``except Exception: return None`` reported such
        recoverable errors as a 404 ("no such image, don't retry") — the
        opposite of what idempotent webhook delivery needs, and it made the
        view's 500 branch unreachable.

        Args:
            payload: Webhook payload data

        Returns:
            Updated CloudflareImage instance, or None if the image is unknown.

        Raises:
            Exception: Any unexpected error while processing a known image is
                propagated to the caller (surfaced as a 500 so Cloudflare
                retries).
        """
        image_id = payload.get("id")
        if not image_id:
            logger.warning("Webhook payload missing image ID")
            return None

        try:
            image = CloudflareImage.objects.get(cloudflare_id=image_id)
        except CloudflareImage.DoesNotExist:
            logger.warning(f"Received webhook for unknown image: {image_id}")
            return None

        # Update image from webhook data. Any error here (e.g. a transient DB
        # failure) propagates to the view's 500 path so Cloudflare retries —
        # it is deliberately NOT caught and reported as an unknown image.
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


# Global service instance
cloudflare_service = CloudflareImagesService()
