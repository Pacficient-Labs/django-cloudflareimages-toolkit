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

    def _delivery_url(self) -> str | None:
        """Return the configured ``DELIVERY_URL``, or ``None``.

        The settings read is wrapped defensively so the URL utilities — and the
        ``transformations`` module that builds on them — keep working as pure
        string helpers even before Django settings are configured (reading
        ``django.conf.settings`` unconfigured raises ``ImproperlyConfigured``).
        """
        try:
            return self._settings.delivery_url
        except Exception:
            return None

    @property
    def uses_custom_domain(self) -> bool:
        """Whether an alternate ``DELIVERY_URL`` is configured."""
        return self._delivery_url() is not None

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
        raw = self._delivery_url()
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
                value to omit the trailing segment entirely. Note that a
                multi-segment ``image_id`` combined with an empty ``variant`` does
                not round-trip through :meth:`extract_image_id`, which treats the
                last segment as the variant; pair custom-path ids with a variant.
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

        Recognizes the shared ``imagedelivery.net`` host and the configured custom
        domain (when ``DELIVERY_URL`` is set). The host must match exactly — a URL
        that merely contains ``imagedelivery.net`` elsewhere in the path does not
        qualify — and for a custom domain with a path prefix the URL must use that
        prefix.
        """
        if not url:
            return False
        host = urlsplit(url if "://" in url else f"//{url}").netloc
        if host == self.DEFAULT_HOST:
            return True
        if self.uses_custom_domain:
            _, custom_host = self._scheme_and_host()
            if custom_host and host == custom_host:
                return self._matches_custom_shape(url)
        return False

    def _matches_custom_shape(self, url: str) -> bool:
        """Whether ``url``'s path matches the configured custom-domain shape.

        With a non-empty path prefix (native custom-domain format), the path must
        equal or start with that prefix, so unrelated assets on the same host
        (e.g. ``/static/logo.png``) are not mistaken for delivery URLs. With an
        empty prefix (Worker reverse-proxy) the whole host serves images, so any
        non-empty path qualifies.
        """
        path = urlsplit(url if "://" in url else f"//{url}").path.strip("/")
        prefix = self.path_prefix
        if prefix:
            return path == prefix or path.startswith(f"{prefix}/")
        return bool(path)

    def extract_image_id(self, url: str) -> str | None:
        """Extract the image id from a delivery URL, or ``None``.

        Handles the shared host, the native custom-domain prefix, and the
        Worker shape, accounting for whether the account hash is present.
        Multi-segment (custom-path) image ids are preserved.

        Note:
            The final path segment is assumed to be the variant. A custom-path
            image id used *without* a variant (e.g. a URL built via
            ``build_url("folder/sub/abc", variant="")``) cannot be distinguished
            from "id + variant" and will lose its last segment here. Pair
            custom-path ids with a variant for reliable round-tripping.
        """
        return self._split_id_variant(url)[0]

    def _split_id_variant(self, url: str) -> tuple[str | None, str | None]:
        """Return ``(image_id, variant)`` for a delivery URL, else ``(None, None)``.

        ``variant`` is ``None`` when the URL carries no trailing variant segment
        (e.g. a no-variant custom URL). This is the single place that splits a
        delivery URL into its id and variant for every other helper.
        """
        if not self.is_delivery_url(url):
            return None, None
        parts = urlsplit(url if "://" in url else f"//{url}")
        # Strip a single leading/trailing slash but keep interior empties visible
        # so malformed paths (e.g. "//id" or "hash//variant") are rejected rather
        # than silently collapsed.
        path = parts.path
        if path.startswith("/"):
            path = path[1:]
        if path.endswith("/"):
            path = path[:-1]
        if not path:
            return None, None
        segs = path.split("/")
        if "" in segs:
            # A missing/empty required segment -> not a valid delivery path.
            return None, None

        if parts.netloc == self.DEFAULT_HOST:
            segs = segs[1:]  # drop the account hash
        else:
            # Configured custom domain: strip the prefix then the optional hash.
            if self.path_prefix:
                prefix_segs = self.path_prefix.split("/")
                if segs[: len(prefix_segs)] == prefix_segs:
                    segs = segs[len(prefix_segs) :]
            if self.include_account_hash and segs:
                segs = segs[1:]

        if len(segs) >= 2:
            # Last segment is the variant/options; the rest is the id.
            return "/".join(segs[:-1]), segs[-1]
        if len(segs) == 1:
            return segs[0], None
        return None, None

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

    def with_options(self, url: str, options: str) -> str:
        """Return a flexible-variant URL applying ``options`` to ``url``.

        When the delivery URL carries a variant segment, that segment is replaced
        by ``options``. When it has no variant (e.g. a no-variant custom URL),
        the options are appended so the image id is preserved rather than
        overwritten. Query string and fragment are preserved.
        """
        _, variant = self._split_id_variant(url)
        parts = urlsplit(url if "://" in url else f"//{url}")
        path = parts.path.rstrip("/")
        if variant is not None and "/" in path.strip("/"):
            new_path = f"{path.rsplit('/', 1)[0]}/{options}"
        else:
            new_path = f"{path}/{options}"
        return urlunsplit(
            (parts.scheme, parts.netloc, new_path, parts.query, parts.fragment)
        )

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
