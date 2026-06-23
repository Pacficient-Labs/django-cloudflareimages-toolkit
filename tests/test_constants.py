"""
Tests for the shared constants SSOT (issue #23).

These lock in that the audited default values live in
``django_cloudflareimages_toolkit.constants`` and are actually *consumed* by the
field, widget, serializer, and service — so a change in one place propagates
instead of silently drifting from a copy elsewhere.
"""

from __future__ import annotations

import pytest

from django_cloudflareimages_toolkit.constants import (
    DEFAULT_ALLOWED_FORMATS,
    MAX_EXPIRY_MINUTES,
    MAX_LIST_PER_PAGE,
    MIN_EXPIRY_MINUTES,
)


def test_default_allowed_formats_value():
    """The shared default is the documented jpeg/png/gif/webp set."""
    assert DEFAULT_ALLOWED_FORMATS == ["jpeg", "png", "gif", "webp"]


def test_field_and_widget_default_to_shared_constant():
    """Both the model field and the form widget default to the SSOT list."""
    from django_cloudflareimages_toolkit.fields import CloudflareImageField
    from django_cloudflareimages_toolkit.widgets import CloudflareImageWidget

    assert CloudflareImageField().allowed_formats == DEFAULT_ALLOWED_FORMATS
    assert CloudflareImageWidget().allowed_formats == DEFAULT_ALLOWED_FORMATS


def test_field_default_does_not_alias_the_constant():
    """Defaulting copies the constant so a field can't mutate the SSOT."""
    from django_cloudflareimages_toolkit.fields import CloudflareImageField

    field = CloudflareImageField()
    field.allowed_formats.append("tiff")
    # The shared constant is unchanged despite mutating one field's list.
    assert DEFAULT_ALLOWED_FORMATS == ["jpeg", "png", "gif", "webp"]


def test_deconstruct_omits_default_allowed_formats():
    """A field left at the default must NOT serialize ``allowed_formats``.

    The audit flagged the old inline ``!= ["jpeg", "png", "gif", "webp"]``
    check as fragile: any drift between that literal and the ``__init__``
    default would change migration output. Comparing against the shared
    constant means the default field stays kwarg-free here.
    """
    from django_cloudflareimages_toolkit.fields import CloudflareImageField

    _, _, _, kwargs = CloudflareImageField().deconstruct()
    assert "allowed_formats" not in kwargs

    # Passing a list equal to the constant is still "the default" → omitted.
    _, _, _, kwargs = CloudflareImageField(
        allowed_formats=list(DEFAULT_ALLOWED_FORMATS)
    ).deconstruct()
    assert "allowed_formats" not in kwargs


def test_deconstruct_keeps_non_default_allowed_formats():
    """A non-default list is still serialized into the migration kwargs."""
    from django_cloudflareimages_toolkit.fields import CloudflareImageField

    _, _, _, kwargs = CloudflareImageField(allowed_formats=["jpeg"]).deconstruct()
    assert kwargs["allowed_formats"] == ["jpeg"]


def test_serializer_expiry_bounds_come_from_constants():
    """The upload serializer validates expiry against the shared bounds."""
    from django_cloudflareimages_toolkit.serializers import (
        ImageUploadRequestSerializer,
    )

    field = ImageUploadRequestSerializer().fields["expiry_minutes"]
    # DRF stores min/max as validators; assert the effective limits match.
    assert field.min_value == MIN_EXPIRY_MINUTES
    assert field.max_value == MAX_EXPIRY_MINUTES


def test_constants_have_expected_cloudflare_limits():
    """Guard the literal Cloudflare API limits in one assertion."""
    assert (MIN_EXPIRY_MINUTES, MAX_EXPIRY_MINUTES) == (2, 360)
    assert MAX_LIST_PER_PAGE == 10000


@pytest.mark.django_db
def test_service_clamps_expiry_to_shared_bounds(monkeypatch):
    """create_direct_upload_url clamps expiry to the shared min/max."""
    import responses
    from django.contrib.auth import get_user_model

    from django_cloudflareimages_toolkit.services import cloudflare_service

    base = "https://api.cloudflare.com/client/v4"
    url = f"{base}/accounts/test-account-id/images/v2/direct_upload"

    user = get_user_model().objects.create(username="clamp-user")

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST,
            url,
            json={
                "success": True,
                "errors": [],
                "result": {"id": "cid", "uploadURL": "https://up/cid"},
            },
            status=200,
        )
        # Far above the max → clamped to MAX_EXPIRY_MINUTES.
        image = cloudflare_service.create_direct_upload_url(
            user=user, expiry_minutes=99999
        )

    # The persisted expiry is at most MAX_EXPIRY_MINUTES from now (allow slack).
    from django.utils import timezone

    delta_minutes = (image.expires_at - timezone.now()).total_seconds() / 60
    assert delta_minutes <= MAX_EXPIRY_MINUTES + 1
