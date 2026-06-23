"""
Tests for CloudflareImageWidget rendering (issues #25 and #22).

The upload flow now lives in the package's template + static assets, not in a
~225-line inline Python string. The widget assembles its ``config`` payload once
and resolves the upload endpoint from its named route
(``cloudflare_images:create-upload-url``) instead of a hardcoded path.
"""

from __future__ import annotations

import json
import re

import pytest
from django.urls import reverse

from django_cloudflareimages_toolkit.widgets import CloudflareImageWidget

# The real upload route (urls.py mounted at /cloudflare-images/ in tests.urls).
UPLOAD_PATH = "/cloudflare-images/api/upload-url/"

# Stale/wrong endpoints the audit (issue #22) flagged as hardcoded.
DEAD_ENDPOINTS = [
    "/cloudflare-images/get-upload-url/",
    "/api/cloudflare-images/upload-url/",
    "django_cloudflare_images",
]


def _config_from_html(html: str, field_id: str = "id_photo") -> dict:
    """Pull the json_script config payload out of the rendered widget HTML."""
    match = re.search(
        rf'<script[^>]*id="{field_id}_config"[^>]*>(.*?)</script>', html, re.S
    )
    assert match, f"json_script config block not found in:\n{html}"
    return json.loads(match.group(1))


def test_endpoint_resolves_from_named_route():
    """The named route resolves to the path the widget should post to."""
    assert reverse("cloudflare_images:create-upload-url") == UPLOAD_PATH


def test_render_uses_template_and_embeds_config():
    html = CloudflareImageWidget().render("photo", "cf-existing")

    assert 'class="cloudflare-image-upload-container"' in html
    assert 'data-cfimg-field="id_photo"' in html
    assert 'name="photo"' in html
    assert "cf-existing" in html  # current value rendered into the hidden input

    config = _config_from_html(html)
    assert config["api_endpoint"] == UPLOAD_PATH
    assert config["allowed_formats"] == ["jpeg", "png", "gif", "webp"]


def test_render_escapes_unsafe_metadata_via_json_script():
    """Metadata is emitted XSS-safe via json_script, not a mark_safe footgun.

    json_script escapes ``<``/``>``/``&``, so metadata can't break out of the
    ``<script type="application/json">`` config block. (The old
    ``mark_safe(json.dumps(...))`` context var, which did NOT escape those
    characters, was removed.)
    """
    html = CloudflareImageWidget(metadata={"x": "<xss>"}).render("photo", None)
    assert "<xss>" not in html  # never injected raw
    assert "\\u003Cxss\\u003E" in html  # json_script-escaped form


def test_render_has_no_inline_upload_javascript():
    """The behaviour comes from the static JS, not inline reimplementation."""
    html = CloudflareImageWidget().render("photo", None)
    assert "async function uploadFile" not in html
    assert "function getCsrfToken" not in html
    assert "addEventListener" not in html


@pytest.mark.parametrize("dead", DEAD_ENDPOINTS)
def test_render_does_not_contain_dead_endpoints(dead):
    html = CloudflareImageWidget().render("photo", None)
    assert dead not in html


def test_config_assembled_in_one_place():
    """get_context's config equals _build_config() — a single assembly point."""
    widget = CloudflareImageWidget(metadata={"k": "v"})
    context = widget.get_context("photo", None, {"id": "id_photo"})
    assert context["widget"]["config"] == widget._build_config()
    assert context["widget"]["config"]["api_endpoint"] == UPLOAD_PATH


def test_fallback_renders_equivalent_markup_without_inline_flow():
    """If the template can't load, the fallback still emits the container +
    config block and still does not reimplement the upload flow inline."""
    widget = CloudflareImageWidget()
    widget.template_name = "does/not/exist.html"  # force the fallback path
    html = widget.render("photo", None)

    assert 'class="cloudflare-image-upload-container"' in html
    assert "async function uploadFile" not in html
    config = _config_from_html(html)
    assert config["api_endpoint"] == UPLOAD_PATH


def test_media_references_static_assets():
    media = str(CloudflareImageWidget().media)
    assert "django_cloudflareimages_toolkit/js/cloudflare_image_widget.js" in media
    assert "django_cloudflareimages_toolkit/css/cloudflare_image_widget.css" in media
