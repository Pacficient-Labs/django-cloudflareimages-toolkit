"""
Django settings for Cloudflare Images Direct Creator Upload.

This module contains the configuration settings needed for the
Cloudflare Images integration.
"""

from django.conf import settings


class CloudflareImagesSettings:
    """Settings configuration for Cloudflare Images."""

    def __init__(self):
        self._settings = getattr(settings, "CLOUDFLARE_IMAGES", {})

    @property
    def account_id(self) -> str:
        """Cloudflare Account ID."""
        account_id = self._settings.get("ACCOUNT_ID")
        if not account_id:
            raise ValueError("CLOUDFLARE_IMAGES['ACCOUNT_ID'] is required")
        return account_id

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
    def default_expiry_minutes(self) -> int:
        """Default expiry time for upload URLs in minutes."""
        return self._settings.get("DEFAULT_EXPIRY_MINUTES", 30)

    @property
    def require_signed_urls(self) -> bool:
        """Whether to require signed URLs by default."""
        return self._settings.get("REQUIRE_SIGNED_URLS", True)

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
