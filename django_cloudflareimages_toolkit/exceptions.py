"""
Custom exceptions for Django Cloudflare Images Toolkit.

This module defines custom exception classes used throughout the toolkit
for better error handling and debugging.
"""


class CloudflareImagesError(Exception):
    """Base exception class for all Cloudflare Images related errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_data: dict | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}


class CloudflareImagesAPIError(CloudflareImagesError):
    """
    Exception raised when the Cloudflare Images API request fails.

    This exception is raised when:
    - API returns an error status code
    - Network request fails
    - Invalid API response format
    - Authentication failures
    """

    pass


class ConfigurationError(CloudflareImagesError):
    """
    Exception raised when configuration is missing or invalid.

    This exception is raised when:
    - Required settings are missing (CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN)
    - Invalid configuration values
    - Missing environment variables
    """

    pass


class ValidationError(CloudflareImagesError):
    """
    Exception raised when validation fails.

    This exception is raised when:
    - Invalid file types or sizes
    - Invalid metadata format
    - Field validation errors
    - Image processing validation failures
    """

    pass


class UploadError(CloudflareImagesError):
    """
    Exception raised when image upload fails.

    This exception is raised when:
    - Upload URL has expired
    - File upload to Cloudflare fails
    - Upload size limits exceeded
    """

    pass


class ImageNotFoundError(CloudflareImagesError):
    """
    Exception raised when an image is not found.

    This exception is raised when:
    - Image ID doesn't exist in Cloudflare
    - Image has been deleted
    - Access denied to image
    """

    pass


class ImageNotReadyError(CloudflareImagesError):
    """
    Exception raised when an image exists but is not ready to be registered.

    This is raised when the image is still a draft -- the upload URL was
    created but no bytes have been uploaded yet, so Cloudflare still reports
    ``draft`` as ``True``. It signals that the ``cloudflare_id`` is real but
    the upload has not completed, so it must not be trusted as finished.
    """


class ImageOwnershipError(CloudflareImagesError):
    """
    Exception raised when a registered image's creator does not match.

    This is raised by ``register_uploaded`` when an ``expected_creator`` is
    supplied and the Cloudflare ``creator`` on the image does not equal it. It
    guards against a caller registering another user's completed image by
    submitting an arbitrary ``cloudflare_id`` from the same account.
    """
