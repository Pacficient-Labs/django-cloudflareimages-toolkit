"""
Tests for endpoint SSOT (issue #22).

Frontend upload/status endpoints must resolve from their named routes, not from
hardcoded strings that drift from urls.py. Covers the ``cf_upload_form`` default
and the removal of the dead admin "check status" route/button.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

import django_cloudflareimages_toolkit
from django_cloudflareimages_toolkit.models import CloudflareImage, ImageUploadStatus
from django_cloudflareimages_toolkit.templatetags.cloudflare_images import (
    cf_upload_form,
)

UPLOAD_PATH = "/cloudflare-images/api/upload-url/"
User = get_user_model()


def test_cf_upload_form_resolves_endpoint_from_named_route():
    """The default api_endpoint comes from reverse() of the named route."""
    ctx = cf_upload_form()
    assert ctx["api_endpoint"] == UPLOAD_PATH
    assert ctx["api_endpoint"] == reverse("cloudflare_images:create-upload-url")


def test_cf_upload_form_explicit_endpoint_is_preserved():
    """An explicitly supplied endpoint overrides the named-route default."""
    ctx = cf_upload_form(api_endpoint="/custom/upload/")
    assert ctx["api_endpoint"] == "/custom/upload/"


def test_admin_static_js_has_no_dead_route():
    """The shipped admin JS no longer references the wrong/nonexistent route."""
    js_path = (
        Path(django_cloudflareimages_toolkit.__file__).parent
        / "static"
        / "admin"
        / "js"
        / "cloudflare_images_admin.js"
    )
    js = js_path.read_text()
    # Wrong app label (django_cloudflare_images) and the unregistered route.
    assert "django_cloudflare_images" not in js
    assert "checkStatus" not in js


@pytest.mark.django_db
def test_admin_changelist_drops_dead_check_button():
    """A PENDING image's row no longer renders the dead checkStatus() link.

    Previously the table view emitted an inline "🔄 Check" link calling
    checkStatus(), which posted to a route that never existed. The per-image
    check now lives only in the bulk admin action.
    """
    admin = User.objects.create_superuser("boss", "boss@example.com", "pw")
    client = Client()
    client.force_login(admin)

    CloudflareImage.objects.create(
        cloudflare_id="cf-pending",
        upload_url="https://upload.example/cf-pending",
        status=ImageUploadStatus.PENDING,
        expires_at=timezone.now() + timedelta(minutes=30),
    )

    url = reverse("admin:django_cloudflareimages_toolkit_cloudflareimage_changelist")
    # Table view is where the per-row actions column is rendered.
    resp = client.get(url, {"view": "table"})
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "checkStatus(" not in body
