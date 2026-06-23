"""
Django settings for Cloudflare Images Direct Creator Upload.

This module contains the configuration settings needed for the
Cloudflare Images integration.
"""

from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string


class CloudflareImagesSettings:
    """Settings configuration for Cloudflare Images."""

    @property
    def _settings(self):
        return getattr(settings, "CLOUDFLARE_IMAGES", {})

    @property
    def account_id(self) -> str:
        """Cloudflare Account ID (used for API calls)."""
        account_id = self._settings.get("ACCOUNT_ID")
        if not account_id:
            raise ValueError("CLOUDFLARE_IMAGES['ACCOUNT_ID'] is required")
        return account_id

    @property
    def account_hash(self) -> str:
        """
        Cloudflare Account Hash (used for image delivery URLs).

        This is different from account_id. Find it in your Cloudflare Images
        dashboard under "Developer Resources" or from any image delivery URL.
        Format: https://imagedelivery.net/<ACCOUNT_HASH>/<IMAGE_ID>/<VARIANT>
        """
        account_hash = self._settings.get("ACCOUNT_HASH")
        if not account_hash:
            raise ValueError(
                "CLOUDFLARE_IMAGES['ACCOUNT_HASH'] is required for image delivery URLs. "
                "Find it in your Cloudflare Images dashboard under Developer Resources."
            )
        return account_hash

    @property
    def api_token(self) -> str:
        """Cloudflare API Token."""
        api_token = self._settings.get("API_TOKEN")
        if not api_token:
            raise ValueError("CLOUDFLARE_IMAGES['API_TOKEN'] is required")
        return api_token

    @property
    def base_url(self) -> str:
        """Cloudflare API base URL."""
        return self._settings.get("BASE_URL", "https://api.cloudflare.com/client/v4")

    @property
    def delivery_url(self) -> str | None:
        """
        Alternate delivery domain to use instead of ``imagedelivery.net``.

        Accepts a bare host (``images.example.com``) or a full base URL
        (``https://images.example.com``). When unset (``None``), delivery URLs
        use Cloudflare's shared ``imagedelivery.net`` domain.

        See :class:`~django_cloudflareimages_toolkit.url_factory.CloudflareImageURLFactory`
        for how this combines with ``DELIVERY_PATH_PREFIX`` and
        ``DELIVERY_INCLUDE_ACCOUNT_HASH``.
        """
        value = self._settings.get("DELIVERY_URL")
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @property
    def delivery_path_prefix(self) -> str:
        """
        Path prefix inserted after a custom ``DELIVERY_URL`` host.

        Defaults to ``"cdn-cgi/imagedelivery"`` (Cloudflare's native
        custom-domain format). Set to an empty string for a Worker-style proxy
        that serves images directly from the domain root. Ignored when
        ``DELIVERY_URL`` is not configured.
        """
        prefix = self._settings.get("DELIVERY_PATH_PREFIX", "cdn-cgi/imagedelivery")
        return str(prefix).strip("/")

    @property
    def delivery_include_account_hash(self) -> bool:
        """
        Whether the account hash appears in custom delivery URLs.

        Defaults to ``True`` (native custom-domain format). Set to ``False`` for
        a Worker-style proxy that injects the account hash itself, producing
        clean ``https://<domain>/<image_id>/<variant>`` URLs. Ignored when
        ``DELIVERY_URL`` is not configured.
        """
        return bool(self._settings.get("DELIVERY_INCLUDE_ACCOUNT_HASH", True))

    @property
    def default_expiry_minutes(self) -> int:
        """Default expiry time for upload URLs in minutes."""
        return self._settings.get("DEFAULT_EXPIRY_MINUTES", 30)

    @property
    def require_signed_urls(self) -> bool:
        """Whether to require signed URLs by default."""
        return self._settings.get("REQUIRE_SIGNED_URLS", True)

    @property
    def default_metadata(self) -> dict:
        """
        Default metadata merged into every direct upload request.

        Per-request metadata keys take precedence over these defaults.
        """
        return self._settings.get("DEFAULT_METADATA", {})

    @property
    def default_creator(self) -> str | None:
        """
        Default Cloudflare ``creator`` value for direct uploads.

        Per-request ``creator`` values take precedence over this default.
        """
        return self._settings.get("DEFAULT_CREATOR")

    @property
    def metadata_factory(self) -> Any:
        """
        Configured metadata factory, or ``None``.

        May be a dotted import path to a callable/class, a class object, an
        instance, or any plain callable. Use :meth:`get_metadata_factory` to
        resolve it to a ready-to-call object.
        """
        return self._settings.get("METADATA_FACTORY")

    def get_metadata_factory(self) -> Callable[..., dict] | None:
        """
        Resolve ``METADATA_FACTORY`` to a callable, or return ``None``.

        Dotted-path strings are imported, classes are instantiated, and plain
        callables/instances are returned as-is.
        """
        factory = self.metadata_factory
        if factory is None:
            return None
        if isinstance(factory, str):
            factory = import_string(factory)
        if isinstance(factory, type):
            factory = factory()
        if not callable(factory):
            raise ValueError(
                "CLOUDFLARE_IMAGES['METADATA_FACTORY'] must resolve to a callable"
            )
        return factory

    @property
    def webhook_secret(self) -> str | None:
        """Webhook secret for validating Cloudflare webhooks."""
        return self._settings.get("WEBHOOK_SECRET")

    @property
    def max_file_size_mb(self) -> int:
        """Maximum file size in MB."""
        return self._settings.get("MAX_FILE_SIZE_MB", 10)


# Global settings instance
cloudflare_settings = CloudflareImagesSettings()
