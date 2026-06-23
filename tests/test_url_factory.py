"""
Tests for the Cloudflare image URL factory and the ``DELIVERY_URL`` setting.

Covers the three supported delivery URL shapes (default ``imagedelivery.net``,
native custom domain, and Worker reverse-proxy), URL rewriting of stored
Cloudflare variants, and integration with the model and field helpers.

These tests use ``unittest``-style ``TestCase`` assertions (matching the other
model/field tests) together with ``override_settings`` for configuration,
rather than bare ``assert`` statements.
"""

from django.test import TestCase, override_settings

from django_cloudflareimages_toolkit.url_factory import (
    CloudflareImageURLFactory,
    image_url_factory,
)

HASH = "test-account-hash"
IMAGE_ID = "abc123"
IMG_URL = f"https://imagedelivery.net/{HASH}/{IMAGE_ID}/public"

# Cloudflare settings shared by every override. Only the keys the URL factory
# actually reads are included; the API token is intentionally omitted since these
# tests never call the Cloudflare API.
BASE_SETTINGS = {
    "ACCOUNT_ID": "test-account-id",
    "ACCOUNT_HASH": HASH,
}

# The Worker reverse-proxy shape: no path prefix and no account hash in the path.
WORKER = {
    "DELIVERY_URL": "cdn.example.com",
    "DELIVERY_PATH_PREFIX": "",
    "DELIVERY_INCLUDE_ACCOUNT_HASH": False,
}


def cf_settings(**overrides):
    """``override_settings`` for ``CLOUDFLARE_IMAGES`` with required keys merged in."""
    return override_settings(CLOUDFLARE_IMAGES={**BASE_SETTINGS, **overrides})


@cf_settings()
class DefaultShapeTest(TestCase):
    """With no DELIVERY_URL configured, behavior matches imagedelivery.net."""

    def test_build_url_default(self):
        self.assertEqual(image_url_factory.build_url(IMAGE_ID), IMG_URL)

    def test_build_url_named_variant(self):
        self.assertEqual(
            image_url_factory.build_url(IMAGE_ID, "thumbnail"),
            f"https://imagedelivery.net/{HASH}/{IMAGE_ID}/thumbnail",
        )

    def test_not_custom_domain(self):
        self.assertFalse(image_url_factory.uses_custom_domain)

    def test_rewrite_is_noop(self):
        self.assertEqual(image_url_factory.rewrite_url(IMG_URL), IMG_URL)

    def test_extract_id(self):
        self.assertEqual(image_url_factory.extract_image_id(IMG_URL), IMAGE_ID)

    def test_extract_id_without_variant(self):
        self.assertEqual(
            image_url_factory.extract_image_id(
                f"https://imagedelivery.net/{HASH}/{IMAGE_ID}"
            ),
            IMAGE_ID,
        )

    def test_split_variant(self):
        base, variant = image_url_factory.split_variant(IMG_URL)
        self.assertEqual(base, f"https://imagedelivery.net/{HASH}/{IMAGE_ID}")
        self.assertEqual(variant, "public")

    def test_is_delivery_url(self):
        self.assertTrue(image_url_factory.is_delivery_url(IMG_URL))
        self.assertFalse(image_url_factory.is_delivery_url("https://example.org/x/y"))


@cf_settings(DELIVERY_URL="images.example.com")
class NativeCustomDomainTest(TestCase):
    """DELIVERY_URL set with the default cdn-cgi/imagedelivery prefix."""

    def test_build_url(self):
        self.assertEqual(
            image_url_factory.build_url(IMAGE_ID),
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/public",
        )

    @cf_settings(DELIVERY_URL="https://images.example.com/")
    def test_full_url_value_is_normalized(self):
        self.assertEqual(
            image_url_factory.build_url(IMAGE_ID),
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/public",
        )

    def test_rewrite(self):
        self.assertEqual(
            image_url_factory.rewrite_url(IMG_URL),
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/public",
        )

    def test_extract_id(self):
        url = image_url_factory.build_url(IMAGE_ID)
        self.assertEqual(image_url_factory.extract_image_id(url), IMAGE_ID)

    def test_is_delivery_url(self):
        self.assertTrue(
            image_url_factory.is_delivery_url(image_url_factory.build_url(IMAGE_ID))
        )
        # The shared host is still recognized.
        self.assertTrue(image_url_factory.is_delivery_url(IMG_URL))
        # An unrelated domain is not.
        self.assertFalse(
            image_url_factory.is_delivery_url("https://other.example.com/x/y")
        )


@cf_settings(**WORKER)
class WorkerShapeTest(TestCase):
    """DELIVERY_URL set with an empty prefix and no account hash in the path."""

    def test_build_url(self):
        self.assertEqual(
            image_url_factory.build_url(IMAGE_ID),
            f"https://cdn.example.com/{IMAGE_ID}/public",
        )

    @override_settings(CLOUDFLARE_IMAGES={**WORKER})
    def test_build_url_does_not_require_account_hash(self):
        # The Worker injects the hash, so building must not touch ACCOUNT_HASH;
        # no ACCOUNT_HASH is configured here at all.
        self.assertEqual(
            image_url_factory.build_url(IMAGE_ID),
            f"https://cdn.example.com/{IMAGE_ID}/public",
        )

    def test_rewrite(self):
        self.assertEqual(
            image_url_factory.rewrite_url(IMG_URL),
            f"https://cdn.example.com/{IMAGE_ID}/public",
        )

    def test_extract_id(self):
        url = f"https://cdn.example.com/{IMAGE_ID}/public"
        self.assertEqual(image_url_factory.extract_image_id(url), IMAGE_ID)


class RewriteDetailsTest(TestCase):
    @cf_settings(**WORKER)
    def test_preserves_query_string(self):
        signed = f"{IMG_URL}?sig=abc&exp=123"
        self.assertEqual(
            image_url_factory.rewrite_url(signed),
            f"https://cdn.example.com/{IMAGE_ID}/public?sig=abc&exp=123",
        )

    @cf_settings(DELIVERY_URL="cdn.example.com")
    def test_noop_on_unrecognized_host(self):
        other = "https://example.org/some/path"
        self.assertEqual(image_url_factory.rewrite_url(other), other)

    @cf_settings(DELIVERY_URL="images.example.com")
    def test_multi_segment_image_id(self):
        url = f"https://imagedelivery.net/{HASH}/folder/sub/{IMAGE_ID}/public"
        self.assertEqual(
            image_url_factory.rewrite_url(url),
            "https://images.example.com/cdn-cgi/imagedelivery/"
            f"{HASH}/folder/sub/{IMAGE_ID}/public",
        )


class ModelIntegrationTest(TestCase):
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

    @cf_settings()
    def test_public_url_default(self):
        image = self._make_image()
        self.assertEqual(
            image.public_url, f"https://imagedelivery.net/{HASH}/{IMAGE_ID}/public"
        )

    @cf_settings(DELIVERY_URL="images.example.com")
    def test_public_and_thumbnail_url_rewritten(self):
        image = self._make_image()
        self.assertEqual(
            image.public_url,
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/public",
        )
        self.assertEqual(
            image.thumbnail_url,
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/thumbnail",
        )

    @cf_settings(**WORKER)
    def test_variant_url_worker_shape(self):
        image = self._make_image()
        self.assertEqual(image.public_url, f"https://cdn.example.com/{IMAGE_ID}/public")


class FieldIntegrationTest(TestCase):
    """CloudflareImageFieldValue.get_url falls back through the factory."""

    @cf_settings(**WORKER)
    def test_get_url_fallback_uses_factory(self):
        from django_cloudflareimages_toolkit.fields import CloudflareImageFieldValue

        value = CloudflareImageFieldValue(IMAGE_ID)
        # No CloudflareImage row exists, so get_url builds via the factory.
        self.assertEqual(
            value.get_url("public"), f"https://cdn.example.com/{IMAGE_ID}/public"
        )


class TransformationsIntegrationTest(TestCase):
    """Transformation utilities recognize custom delivery domains."""

    @cf_settings(DELIVERY_URL="images.example.com")
    def test_transform_recognizes_custom_domain(self):
        from django_cloudflareimages_toolkit.transformations import (
            CloudflareImageTransform,
        )

        base = (
            f"https://images.example.com/cdn-cgi/imagedelivery/{HASH}/{IMAGE_ID}/public"
        )
        url = CloudflareImageTransform(base).width(300).height(200).build()
        self.assertEqual(
            url,
            "https://images.example.com/cdn-cgi/imagedelivery/"
            f"{HASH}/{IMAGE_ID}/width=300,height=200",
        )

    @cf_settings(**WORKER)
    def test_utils_recognize_custom_domain(self):
        from django_cloudflareimages_toolkit.transformations import CloudflareImageUtils

        url = f"https://cdn.example.com/{IMAGE_ID}/public"
        self.assertTrue(CloudflareImageUtils.is_cloudflare_image_url(url))
        self.assertEqual(CloudflareImageUtils.extract_image_id(url), IMAGE_ID)
        self.assertTrue(CloudflareImageUtils.validate_image_url(url))


class DeterminismAndIdempotencyTest(TestCase):
    """Guard the deterministic and idempotent guarantees of the factory."""

    ALL_SHAPES = [
        {},  # default imagedelivery.net
        {"DELIVERY_URL": "images.example.com"},  # native custom domain
        WORKER,  # Worker reverse-proxy
    ]

    def test_build_url_is_deterministic(self):
        for overrides in self.ALL_SHAPES:
            with self.subTest(overrides=overrides), cf_settings(**overrides):
                first = image_url_factory.build_url(IMAGE_ID, "public")
                second = image_url_factory.build_url(IMAGE_ID, "public")
                self.assertEqual(first, second)

    def test_rewrite_is_idempotent(self):
        # Re-running rewrite on an already-rewritten URL must not change it.
        for overrides in self.ALL_SHAPES[1:]:
            with self.subTest(overrides=overrides), cf_settings(**overrides):
                once = image_url_factory.rewrite_url(IMG_URL)
                twice = image_url_factory.rewrite_url(once)
                self.assertEqual(once, twice)

    @cf_settings(DELIVERY_URL="images.example.com")
    def test_rewrite_does_not_double_apply_prefix(self):
        rewritten = image_url_factory.rewrite_url(IMG_URL)
        # A URL already on the custom host is left untouched.
        self.assertEqual(image_url_factory.rewrite_url(rewritten), rewritten)


class SingletonTest(TestCase):
    def test_singleton_is_factory_instance(self):
        self.assertIsInstance(image_url_factory, CloudflareImageURLFactory)
