"""
Image URL factory for Cloudflare Images Toolkit.

This module centralizes the construction, recognition, extraction, and rewriting
of Cloudflare Images delivery URLs. By default, URLs use Cloudflare's shared
``imagedelivery.net`` domain, but site admins can configure an alternate delivery
domain via the ``DELIVERY_URL`` setting (see
:mod:`django_cloudflareimages_toolkit.settings`).

Three URL shapes are supported, selected purely by configuration:

1. **Default** (no ``DELIVERY_URL``)::

       https://imagedelivery.net/<account_hash>/<image_id>/<variant>

2. **Native custom domain** (``DELIVERY_URL`` set, default path prefix)::

       https://<domain>/cdn-cgi/imagedelivery/<account_hash>/<image_id>/<variant>

3. **Worker reverse-proxy** (``DELIVERY_URL`` set, empty prefix, hash excluded)::

       https://<domain>/<image_id>/<variant>

The factory reads settings live on every call, so configuration overrides in
tests and at runtime take effect immediately.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from .settings import CloudflareImagesSettings, cloudflare_settings


class CloudflareImageURLFactory:
    """Single source of truth for Cloudflare Images delivery URLs.

    The factory builds delivery URLs from their components, recognizes whether
    an arbitrary URL is a delivery URL, extracts the image id from one, and
    rewrites Cloudflare's ``imagedelivery.net`` URLs into the configured shape.

    All behavior is driven by the ``DELIVERY_URL``, ``DELIVERY_PATH_PREFIX``, and
    ``DELIVERY_INCLUDE_ACCOUNT_HASH`` settings. When ``DELIVERY_URL`` is not
    configured, every method preserves the historical ``imagedelivery.net``
    behavior.
    """

    DEFAULT_HOST = "imagedelivery.net"
    DEFAULT_SCHEME = "https"

    def __init__(self, settings: CloudflareImagesSettings | None = None) -> None:
        """Initialize the factory.

        Args:
            settings: A settings object exposing ``delivery_url``,
                ``delivery_path_prefix``, ``delivery_include_account_hash``, and
                ``account_hash``. Defaults to the global ``cloudflare_settings``
                singleton.
        """
        self._settings: CloudflareImagesSettings = (
            settings if settings is not None else cloudflare_settings
        )

    # ------------------------------------------------------------------ config

    @property
    def uses_custom_domain(self) -> bool:
        """Whether an alternate ``DELIVERY_URL`` is configured."""
        return self._settings.delivery_url is not None

    @property
    def path_prefix(self) -> str:
        """Normalized path prefix for custom-domain URLs (``""`` when default)."""
        if not self.uses_custom_domain:
            return ""
        return self._settings.delivery_path_prefix

    @property
    def include_account_hash(self) -> bool:
        """Whether the account hash appears in the path of built URLs."""
        if not self.uses_custom_domain:
            return True
        return self._settings.delivery_include_account_hash

    def _scheme_and_host(self) -> tuple[str, str]:
        """Resolve the ``(scheme, host)`` for delivery URLs.

        Accepts a bare host (``images.example.com``) or a full base URL
        (``https://images.example.com``). Falls back to the shared
        ``imagedelivery.net`` host when no ``DELIVERY_URL`` is configured.
        """
        raw = self._settings.delivery_url
        if not raw:
            return self.DEFAULT_SCHEME, self.DEFAULT_HOST
        raw = raw.strip()
        if "://" in raw:
            parts = urlsplit(raw)
            scheme = parts.scheme or self.DEFAULT_SCHEME
            host = (parts.netloc or parts.path).strip("/")
        else:
            scheme = self.DEFAULT_SCHEME
            # Ignore any accidental path; paths belong in DELIVERY_PATH_PREFIX.
            host = raw.strip("/").split("/", 1)[0]
        return scheme, host

    # ------------------------------------------------------------------- build

    def base_url(self, account_hash: str | None = None) -> str:
        """Return the delivery URL prefix up to (but excluding) the image id.

        Args:
            account_hash: Override for the account hash. Defaults to
                ``cloudflare_settings.account_hash`` when the configured shape
                includes the hash.
        """
        scheme, host = self._scheme_and_host()
        segments: list[str] = []
        prefix = self.path_prefix
        if prefix:
            segments.append(prefix)
        if self.include_account_hash:
            resolved = account_hash or self._settings.account_hash
            segments.append(str(resolved).strip("/"))
        path = "/".join(segments)
        if path:
            return f"{scheme}://{host}/{path}"
        return f"{scheme}://{host}"

    def build_url(
        self,
        image_id: str,
        variant: str = "public",
        account_hash: str | None = None,
    ) -> str:
        """Build a full delivery URL honoring the configured shape.

        Args:
            image_id: The Cloudflare image id (may contain ``/`` for custom paths).
            variant: The variant name or flexible-variant options. Pass an empty
                value to omit the trailing segment entirely.
            account_hash: Optional account-hash override.

        Returns:
            The fully-qualified delivery URL.
        """
        base = self.base_url(account_hash=account_hash)
        image_id = str(image_id).strip("/")
        variant = variant.strip("/") if variant else ""
        if variant:
            return f"{base}/{image_id}/{variant}"
        return f"{base}/{image_id}"

    # ----------------------------------------------------------------- inspect

    def is_delivery_url(self, url: str) -> bool:
        """Return ``True`` if ``url`` is a Cloudflare Images delivery URL.

        Recognizes both the shared ``imagedelivery.net`` host and the configured
        custom domain (when ``DELIVERY_URL`` is set).
        """
        if not url:
            return False
        if self.DEFAULT_HOST in url:
            return True
        if self.uses_custom_domain:
            _, host = self._scheme_and_host()
            parts = urlsplit(url if "://" in url else f"//{url}")
            return bool(host) and parts.netloc == host
        return False

    def extract_image_id(self, url: str) -> str | None:
        """Extract the image id from a delivery URL, or ``None``.

        Handles the shared host, the native custom-domain prefix, and the
        Worker shape, accounting for whether the account hash is present.
        Multi-segment (custom-path) image ids are preserved.
        """
        if not self.is_delivery_url(url):
            return None
        parts = urlsplit(url if "://" in url else f"//{url}")
        path = parts.path.strip("/")
        if not path:
            return None
        segments = path.split("/")

        if parts.netloc == self.DEFAULT_HOST or (
            not parts.netloc and self.DEFAULT_HOST in url
        ):
            # imagedelivery.net/<hash>/<id...>[/<variant>]
            return self._image_id_from_segments(
                segments, has_prefix=False, has_hash=True
            )

        # Configured custom domain.
        return self._image_id_from_segments(
            segments,
            has_prefix=bool(self.path_prefix),
            has_hash=self.include_account_hash,
        )

    def _image_id_from_segments(
        self, segments: list[str], *, has_prefix: bool, has_hash: bool
    ) -> str | None:
        """Resolve the image id from path segments for the imagedelivery shape."""
        segs = list(segments)
        if has_prefix:
            prefix_segs = self.path_prefix.split("/")
            if segs[: len(prefix_segs)] == prefix_segs:
                segs = segs[len(prefix_segs) :]
        if has_hash and segs:
            segs = segs[1:]  # drop the account hash
        if len(segs) >= 2:
            # Last segment is the variant/options; the rest is the id.
            return "/".join(segs[:-1])
        if len(segs) == 1:
            return segs[0]
        return None

    def split_variant(self, url: str) -> tuple[str, str | None]:
        """Split a delivery URL into ``(base_without_last_segment, last_segment)``.

        Useful for swapping a named variant for flexible-variant options. The
        query string and fragment are dropped from the returned base.
        """
        parts = urlsplit(url)
        path = parts.path.rstrip("/")
        if "/" not in path.strip("/"):
            return url, None
        head, _, last = path.rpartition("/")
        base = urlunsplit((parts.scheme, parts.netloc, head, "", ""))
        return base, (last or None)

    # ----------------------------------------------------------------- rewrite

    def rewrite_url(self, url: str) -> str:
        """Rewrite a Cloudflare ``imagedelivery.net`` URL into the configured shape.

        Cloudflare always returns variant URLs on the shared ``imagedelivery.net``
        host; this rewrites them to the configured custom domain. The query string
        and fragment (e.g. signed-URL parameters) are preserved.

        Returns the URL unchanged when no ``DELIVERY_URL`` is configured or when
        ``url`` is not a shared-host delivery URL.
        """
        if not url or not self.uses_custom_domain:
            return url
        parts = urlsplit(url)
        if parts.netloc != self.DEFAULT_HOST:
            # Only the shared host is rewritten; anything else is left as-is.
            return url
        path = parts.path.strip("/")
        segments = path.split("/") if path else []
        if len(segments) < 2:
            return url
        account_hash = segments[0]
        if len(segments) >= 3:
            image_id = "/".join(segments[1:-1])
            variant = segments[-1]
        else:
            image_id = segments[1]
            variant = ""
        rebuilt = self.build_url(image_id, variant, account_hash=account_hash)
        if parts.query or parts.fragment:
            rebuilt_parts = urlsplit(rebuilt)
            rebuilt = urlunsplit(
                (
                    rebuilt_parts.scheme,
                    rebuilt_parts.netloc,
                    rebuilt_parts.path,
                    parts.query,
                    parts.fragment,
                )
            )
        return rebuilt


# Global factory instance.
image_url_factory = CloudflareImageURLFactory()
