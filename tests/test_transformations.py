"""
Tests for transformation determinism (issue #24).

Builder call order must not affect the generated URL. Cloudflare parses image
options order-independently, so two semantically identical transforms must
serialize to byte-identical URLs — otherwise the CDN caches them as distinct
objects (halving the hit rate for the same render) and the output becomes
non-reproducible and hard to assert on.
"""

from __future__ import annotations

from django_cloudflareimages_toolkit.transformations import (
    CloudflareImageTransform,
    CloudflareImageVariants,
)


def test_option_order_independent_imagedelivery():
    """.width().height() and .height().width() yield the same delivery URL."""
    base = "https://imagedelivery.net/acct-hash/image-id/public"
    a = CloudflareImageTransform(base).width(300).height(200).quality(85).build()
    b = CloudflareImageTransform(base).quality(85).height(200).width(300).build()
    assert a == b


def test_option_order_independent_cdn_cgi_zone():
    """Order independence also holds for the /cdn-cgi/image/ (zone) format."""
    path = "path/to/image.jpg"
    a = (
        CloudflareImageTransform(path, zone="example.com")
        .width(300)
        .height(200)
        .build()
    )
    b = (
        CloudflareImageTransform(path, zone="example.com")
        .height(200)
        .width(300)
        .build()
    )
    assert a == b


def test_options_string_is_alphabetical():
    """Options serialize alphabetically by key regardless of call order."""
    base = "https://imagedelivery.net/acct-hash/image-id/public"
    transform = (
        CloudflareImageTransform(base).quality(85).width(300).fit("cover").height(200)
    )
    assert (
        transform._build_options_string() == "fit=cover,height=200,quality=85,width=300"
    )


def test_built_url_uses_sorted_options_segment():
    """The flexible-variant URL ends with the canonical, sorted option string."""
    base = "https://imagedelivery.net/acct-hash/image-id/public"
    url = CloudflareImageTransform(base).height(200).width(300).build()
    assert url.endswith("/height=200,width=300")


def test_variants_helper_is_order_stable():
    """The predefined variants build deterministically too (same input → same URL)."""
    base = "https://imagedelivery.net/acct-hash/image-id/public"
    assert CloudflareImageVariants.thumbnail(
        base, 150
    ) == CloudflareImageVariants.thumbnail(base, 150)
