"""
Tests for the Cloudflare image URL factory and the ``DELIVERY_URL`` setting.

Covers the three supported delivery URL shapes (default ``imagedelivery.net``,
native custom domain, and Worker reverse-proxy), URL rewriting of stored
Cloudflare variants, and integration with the model and field helpers.
"""

import pytest

from django_cloudflareimages_toolkit.settings import cloudflare_settings
from django_cloudflareimages_toolkit.url_factory import (
    CloudflareImageURLFactory,
    image_url_factory,
)

HASH = "test-account-hash"
IMAGE_ID = "abc123"
IMG_URL = f"https://imagedelivery.net/{HASH}/{IMAGE_ID}/public"


@pytest.fixture
def factory():
    """A fresh factory bound to the global settings singleton."""
    return CloudflareImageURLFactory()


def set_delivery(monkeypatch, **values):
    """Override DELIVERY_* settings for the duration of a test."""
    for key, value in values.items():
        monkeypatch.setitem(cloudflare_settings._settings, key, value)


class TestDefaultShape:
    """With no DELIVERY_URL configured, behavior matches imagedelivery.net."""

    def test_build_url_default(self, factory):
        assert factory.build_url(IMAGE_ID) == IMG_URL

    def test_build_url_named_variant(self, factory):
        assert (
            factory.build_url(IMAGE_ID, "thumbnail")
            == f"https://imagedelivery.net/{HASH}/{IMAGE_ID}/thumbnail"
        )

    def test_not_custom_domain(self, factory):
        assert factory.uses_custom_domain is False

    def test_rewrite_is_noop(self, factory):
        assert factory.rewrite_url(IMG_URL) == IMG_URL

    def test_extract_id(self, factory):
        assert factory.extract_image_id(IMG_URL) == IMAGE_ID

    def test_extract_id_without_variant(self, factory):
        assert (
            factory.extract_image_id(f"https://imagedelivery.net/{HASH}/{IMAGE_ID}")
            == IMAGE_ID
        )

    def test_split_variant(self, factory):
        base, variant = factory.split_variant(IMG_URL)
        assert base == f"https://imagedelivery.net/{HASH}/{IMAGE_ID}"
        assert variant == "public"

    def test_is_delivery_url(self, factory):
        assert factory.is_delivery_url(IMG_URL)
        assert not factory.is_delivery_url("https://example.org/x/y")


class TestNativeCustomDomain:
    """DELIVERY_URL set with the default cdn-cgi/imagedelivery prefix."""

    def test_build_url(self, factory, monkeypatch):
        set_delivery(monkeypatch, DELIVERY_URL="images.example.com")
        assert factory.build_url(IMAGE_ID) == (
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/public"
        )

    def test_full_url_value_is_normalized(self, factory, monkeypatch):
        set_delivery(monkeypatch, DELIVERY_URL="https://images.example.com/")
        assert factory.build_url(IMAGE_ID) == (
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/public"
        )

    def test_rewrite(self, factory, monkeypatch):
        set_delivery(monkeypatch, DELIVERY_URL="images.example.com")
        assert factory.rewrite_url(IMG_URL) == (
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/public"
        )

    def test_extract_id(self, factory, monkeypatch):
        set_delivery(monkeypatch, DELIVERY_URL="images.example.com")
        url = factory.build_url(IMAGE_ID)
        assert factory.extract_image_id(url) == IMAGE_ID

    def test_is_delivery_url(self, factory, monkeypatch):
        set_delivery(monkeypatch, DELIVERY_URL="images.example.com")
        assert factory.is_delivery_url(factory.build_url(IMAGE_ID))
        # The shared host is still recognized.
        assert factory.is_delivery_url(IMG_URL)
        # An unrelated domain is not.
        assert not factory.is_delivery_url("https://other.example.com/x/y")


class TestWorkerShape:
    """DELIVERY_URL set with an empty prefix and no account hash in the path."""

    @pytest.fixture(autouse=True)
    def _worker_settings(self, monkeypatch):
        set_delivery(
            monkeypatch,
            DELIVERY_URL="cdn.example.com",
            DELIVERY_PATH_PREFIX="",
            DELIVERY_INCLUDE_ACCOUNT_HASH=False,
        )

    def test_build_url(self, factory):
        assert (
            factory.build_url(IMAGE_ID) == f"https://cdn.example.com/{IMAGE_ID}/public"
        )

    def test_build_url_does_not_require_account_hash(self, factory, monkeypatch):
        # The Worker injects the hash, so building must not touch ACCOUNT_HASH.
        monkeypatch.delitem(
            cloudflare_settings._settings, "ACCOUNT_HASH", raising=False
        )
        assert (
            factory.build_url(IMAGE_ID) == f"https://cdn.example.com/{IMAGE_ID}/public"
        )

    def test_rewrite(self, factory):
        assert (
            factory.rewrite_url(IMG_URL) == f"https://cdn.example.com/{IMAGE_ID}/public"
        )

    def test_extract_id(self, factory):
        url = f"https://cdn.example.com/{IMAGE_ID}/public"
        assert factory.extract_image_id(url) == IMAGE_ID


class TestRewriteDetails:
    def test_preserves_query_string(self, factory, monkeypatch):
        set_delivery(
            monkeypatch,
            DELIVERY_URL="cdn.example.com",
            DELIVERY_PATH_PREFIX="",
            DELIVERY_INCLUDE_ACCOUNT_HASH=False,
        )
        signed = f"{IMG_URL}?sig=abc&exp=123"
        assert (
            factory.rewrite_url(signed)
            == f"https://cdn.example.com/{IMAGE_ID}/public?sig=abc&exp=123"
        )

    def test_noop_on_unrecognized_host(self, factory, monkeypatch):
        set_delivery(monkeypatch, DELIVERY_URL="cdn.example.com")
        other = "https://example.org/some/path"
        assert factory.rewrite_url(other) == other

    def test_multi_segment_image_id(self, factory, monkeypatch):
        set_delivery(monkeypatch, DELIVERY_URL="images.example.com")
        url = f"https://imagedelivery.net/{HASH}/folder/sub/{IMAGE_ID}/public"
        assert factory.rewrite_url(url) == (
            "https://images.example.com/cdn-cgi/imagedelivery/"
            f"{HASH}/folder/sub/{IMAGE_ID}/public"
        )


class TestModelIntegration:
    """CloudflareImage URL helpers honor the configured delivery domain."""

    def _make_image(self):
        from django_cloudflareimages_toolkit.models import CloudflareImage

        return CloudflareImage(
            cloudflare_id=IMAGE_ID,
            variants=[
                f"https://imagedelivery.net/{HASH}/{IMAGE_ID}/public",
                f"https://imagedelivery.net/{HASH}/{IMAGE_ID}/thumbnail",
            ],
        )

    def test_public_url_default(self):
        image = self._make_image()
        assert image.public_url == f"https://imagedelivery.net/{HASH}/{IMAGE_ID}/public"

    def test_public_and_thumbnail_url_rewritten(self, monkeypatch):
        set_delivery(monkeypatch, DELIVERY_URL="images.example.com")
        image = self._make_image()
        assert image.public_url == (
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/public"
        )
        assert image.thumbnail_url == (
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/thumbnail"
        )

    def test_variant_url_worker_shape(self, monkeypatch):
        set_delivery(
            monkeypatch,
            DELIVERY_URL="cdn.example.com",
            DELIVERY_PATH_PREFIX="",
            DELIVERY_INCLUDE_ACCOUNT_HASH=False,
        )
        image = self._make_image()
        assert image.public_url == f"https://cdn.example.com/{IMAGE_ID}/public"


@pytest.mark.django_db
class TestFieldIntegration:
    """CloudflareImageFieldValue.get_url falls back through the factory."""

    def test_get_url_fallback_uses_factory(self, monkeypatch):
        from django_cloudflareimages_toolkit.fields import CloudflareImageFieldValue

        set_delivery(
            monkeypatch,
            DELIVERY_URL="cdn.example.com",
            DELIVERY_PATH_PREFIX="",
            DELIVERY_INCLUDE_ACCOUNT_HASH=False,
        )
        value = CloudflareImageFieldValue(IMAGE_ID)
        # No CloudflareImage row exists, so get_url builds via the factory.
        assert value.get_url("public") == f"https://cdn.example.com/{IMAGE_ID}/public"


class TestTransformationsIntegration:
    """Transformation utilities recognize custom delivery domains."""

    def test_transform_recognizes_custom_domain(self, monkeypatch):
        from django_cloudflareimages_toolkit.transformations import (
            CloudflareImageTransform,
        )

        set_delivery(monkeypatch, DELIVERY_URL="images.example.com")
        base = (
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/public"
        )
        url = CloudflareImageTransform(base).width(300).height(200).build()
        assert url == (
            "https://images.example.com/cdn-cgi/imagedelivery/"
            f"{HASH}/{IMAGE_ID}/width=300,height=200"
        )

    def test_utils_recognize_custom_domain(self, monkeypatch):
        from django_cloudflareimages_toolkit.transformations import CloudflareImageUtils

        set_delivery(
            monkeypatch,
            DELIVERY_URL="cdn.example.com",
            DELIVERY_PATH_PREFIX="",
            DELIVERY_INCLUDE_ACCOUNT_HASH=False,
        )
        url = f"https://cdn.example.com/{IMAGE_ID}/public"
        assert CloudflareImageUtils.is_cloudflare_image_url(url)
        assert CloudflareImageUtils.extract_image_id(url) == IMAGE_ID
        assert CloudflareImageUtils.validate_image_url(url)


class TestDeterminismAndIdempotency:
    """Guard the deterministic and idempotent guarantees of the factory."""

    ALL_SHAPES = [
        {},  # default imagedelivery.net
        {"DELIVERY_URL": "images.example.com"},  # native custom domain
        {
            "DELIVERY_URL": "cdn.example.com",
            "DELIVERY_PATH_PREFIX": "",
            "DELIVERY_INCLUDE_ACCOUNT_HASH": False,
        },  # Worker reverse-proxy
    ]

    @pytest.mark.parametrize("shape", ALL_SHAPES)
    def test_build_url_is_deterministic(self, factory, monkeypatch, shape):
        set_delivery(monkeypatch, **shape)
        first = factory.build_url(IMAGE_ID, "public")
        second = factory.build_url(IMAGE_ID, "public")
        assert first == second

    @pytest.mark.parametrize("shape", ALL_SHAPES[1:])
    def test_rewrite_is_idempotent(self, factory, monkeypatch, shape):
        set_delivery(monkeypatch, **shape)
        once = factory.rewrite_url(IMG_URL)
        twice = factory.rewrite_url(once)
        # Re-running on an already-rewritten URL must not change it.
        assert once == twice

    def test_rewrite_does_not_double_apply_prefix(self, factory, monkeypatch):
        set_delivery(monkeypatch, DELIVERY_URL="images.example.com")
        rewritten = factory.rewrite_url(IMG_URL)
        # A URL already on the custom host is left untouched.
        assert factory.rewrite_url(rewritten) == rewritten


def test_singleton_is_factory_instance():
    assert isinstance(image_url_factory, CloudflareImageURLFactory)
