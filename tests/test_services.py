"""
Tests for CloudflareImagesService upload configuration and safe registration.

Covers:
  * FIX 1 - settings-backed defaults (DEFAULT_METADATA / DEFAULT_CREATOR /
    require_signed_urls / expiry) and that per-request params override them,
    with metadata + creator both sent to Cloudflare and persisted locally.
  * FIX 2 - CloudflareImage.objects.register_uploaded(): success path plus the
    missing-image and still-draft failure paths.
  * FIX 3 - the pluggable ImageMetadataFactory (class via dotted path and a
    plain callable), merge precedence, and the context it receives.

The Cloudflare API is mocked at the HTTP boundary with the ``responses``
library (declared in the project's ``test`` extra). Settings are overridden by
mutating the dict the singleton snapshots, mirroring tests/test_webhook_view.py.
"""

from __future__ import annotations

import pytest
import responses
from django.contrib.auth import get_user_model

from django_cloudflareimages_toolkit.exceptions import (
    CloudflareImagesError,
    ImageNotFoundError,
    ImageNotReadyError,
)
from django_cloudflareimages_toolkit.metadata import ImageMetadataFactory
from django_cloudflareimages_toolkit.models import (
    CloudflareImage,
    ImageUploadStatus,
)
from django_cloudflareimages_toolkit.services import cloudflare_service
from django_cloudflareimages_toolkit.settings import cloudflare_settings

BASE = "https://api.cloudflare.com/client/v4"
ACCOUNT = "test-account-id"
DIRECT_UPLOAD_URL = f"{BASE}/accounts/{ACCOUNT}/images/v2/direct_upload"


def _image_url(cloudflare_id: str) -> str:
    return f"{BASE}/accounts/{ACCOUNT}/images/v1/{cloudflare_id}"


def _mock_direct_upload(cloudflare_id: str = "cf-test-id") -> None:
    responses.add(
        responses.POST,
        DIRECT_UPLOAD_URL,
        json={
            "success": True,
            "errors": [],
            "messages": [],
            "result": {
                "id": cloudflare_id,
                "uploadURL": f"https://upload.imagedelivery.net/{cloudflare_id}",
            },
        },
        status=200,
    )


def _last_upload_body() -> str:
    """Return the most recent direct_upload request body as text."""
    body = responses.calls[-1].request.body
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    # requests may hand responses a bytes-producing iterator for multipart.
    if hasattr(body, "read"):
        return body.read().decode("utf-8", errors="replace")
    return str(body)


@pytest.fixture
def user(db):
    return get_user_model().objects.create(username="alice")


# ---------------------------------------------------------------------------
# FIX 1 - configurable defaults + persistence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUploadDefaults:
    @responses.activate
    def test_settings_defaults_applied_and_persisted(self, monkeypatch, user):
        """DEFAULT_METADATA / DEFAULT_CREATOR flow into the request and record."""
        monkeypatch.setitem(
            cloudflare_settings._settings, "DEFAULT_METADATA", {"env": "prod"}
        )
        monkeypatch.setitem(
            cloudflare_settings._settings, "DEFAULT_CREATOR", "default-creator"
        )
        _mock_direct_upload()

        image = cloudflare_service.create_direct_upload_url(user=user)

        # Persisted onto the local record.
        assert image.metadata == {"env": "prod"}
        assert image.creator == "default-creator"

        # Sent to Cloudflare in the multipart form body.
        body = _last_upload_body()
        assert "default-creator" in body
        assert '"env": "prod"' in body or '\\"env\\": \\"prod\\"' in body

    @responses.activate
    def test_per_request_overrides_defaults(self, monkeypatch, user):
        """Per-request metadata/creator/flags beat the settings defaults."""
        monkeypatch.setitem(
            cloudflare_settings._settings,
            "DEFAULT_METADATA",
            {"env": "prod", "team": "core"},
        )
        monkeypatch.setitem(
            cloudflare_settings._settings, "DEFAULT_CREATOR", "default-creator"
        )
        monkeypatch.setitem(cloudflare_settings._settings, "REQUIRE_SIGNED_URLS", True)
        _mock_direct_upload()

        image = cloudflare_service.create_direct_upload_url(
            user=user,
            metadata={"env": "staging"},
            creator="request-creator",
            require_signed_urls=False,
            expiry_minutes=120,
        )

        # Per-request key wins; default-only key survives the merge.
        assert image.metadata == {"env": "staging", "team": "core"}
        assert image.creator == "request-creator"
        assert image.require_signed_urls is False

        body = _last_upload_body()
        assert "request-creator" in body
        assert "default-creator" not in body
        assert "requiresignedurls" in body.lower()
        assert "false" in body.lower()

    @responses.activate
    def test_metadata_and_creator_sent_and_round_tripped(self, monkeypatch, user):
        """No defaults configured: explicit values still sent + persisted."""
        monkeypatch.setitem(cloudflare_settings._settings, "DEFAULT_METADATA", {})
        monkeypatch.setitem(cloudflare_settings._settings, "DEFAULT_CREATOR", None)
        _mock_direct_upload(cloudflare_id="round-trip-id")

        image = cloudflare_service.create_direct_upload_url(
            user=user,
            metadata={"category": "avatar"},
            creator="user-42",
        )

        assert image.cloudflare_id == "round-trip-id"
        assert image.metadata == {"category": "avatar"}
        assert image.creator == "user-42"

        body = _last_upload_body()
        assert "user-42" in body
        assert "avatar" in body
        # The request hit the v2 multipart direct_upload endpoint.
        assert responses.calls[-1].request.url == DIRECT_UPLOAD_URL

    @responses.activate
    def test_non_dict_metadata_raises_typed_error_not_500(self, user):
        """A non-dict metadata is rejected before the spread-merge (no TypeError)."""
        _mock_direct_upload()
        with pytest.raises(CloudflareImagesError):
            cloudflare_service.create_direct_upload_url(
                user=user, metadata=["not", "a", "dict"]
            )
        # No request was made to Cloudflare.
        assert len(responses.calls) == 0


# ---------------------------------------------------------------------------
# FIX 3 - pluggable metadata factory
# ---------------------------------------------------------------------------


class RecordingMetadataFactory(ImageMetadataFactory):
    """Test factory that embeds what it received into the returned metadata.

    Observability is encoded into the (persisted) output rather than a class
    attribute because the test harness imports this module under two names
    (``test_services`` for the running test, ``tests.test_services`` for the
    dotted-path import), which would otherwise be two distinct class objects.
    """

    def get_metadata(self, *, metadata, user=None, custom_id=None, creator=None, **ctx):
        result = dict(metadata)
        result["seen_keys"] = sorted(metadata.keys())
        result["seen_user"] = getattr(user, "username", None)
        result["seen_creator"] = creator
        result["factory_added"] = "yes"
        result["env"] = "factory-wins"  # override any inbound 'env'
        return result


def callable_metadata_factory(*, metadata, **ctx):
    """Plain-callable factory form."""
    result = dict(metadata)
    result["via_callable"] = True
    return result


@pytest.mark.django_db
class TestMetadataFactory:
    @responses.activate
    def test_factory_merges_sent_and_persisted_with_precedence(self, monkeypatch, user):
        monkeypatch.setitem(
            cloudflare_settings._settings, "DEFAULT_METADATA", {"env": "default"}
        )
        monkeypatch.setitem(
            cloudflare_settings._settings, "DEFAULT_CREATOR", "default-creator"
        )
        monkeypatch.setitem(
            cloudflare_settings._settings,
            "METADATA_FACTORY",
            "tests.test_services.RecordingMetadataFactory",
        )
        _mock_direct_upload()

        image = cloudflare_service.create_direct_upload_url(
            user=user,
            metadata={"env": "request", "user_key": "u"},
            custom_id=None,
        )

        # The factory saw DEFAULT_METADATA merged with per-request metadata,
        # plus the resolved user and creator context.
        assert image.metadata["seen_keys"] == ["env", "user_key"]
        assert image.metadata["seen_user"] == "alice"
        assert image.metadata["seen_creator"] == "default-creator"

        # Factory output has the final say (overrode 'env') and is persisted.
        assert image.metadata["env"] == "factory-wins"
        assert image.metadata["user_key"] == "u"
        assert image.metadata["factory_added"] == "yes"

        body = _last_upload_body()
        assert "factory_added" in body
        assert "factory-wins" in body

    @responses.activate
    def test_plain_callable_factory(self, monkeypatch, user):
        monkeypatch.setitem(
            cloudflare_settings._settings,
            "METADATA_FACTORY",
            "tests.test_services.callable_metadata_factory",
        )
        _mock_direct_upload()

        image = cloudflare_service.create_direct_upload_url(
            user=user, metadata={"a": 1}
        )

        assert image.metadata["via_callable"] is True
        assert image.metadata["a"] == 1


# ---------------------------------------------------------------------------
# FIX 2 - safe register_uploaded
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRegisterUploaded:
    @responses.activate
    def test_success_populates_record(self, user):
        cid = "uploaded-image-id"
        responses.add(
            responses.GET,
            _image_url(cid),
            json={
                "success": True,
                "errors": [],
                "messages": [],
                "result": {
                    "id": cid,
                    "filename": "photo.jpg",
                    "uploaded": "2025-01-01T00:00:00Z",
                    "requireSignedURLs": False,
                    "draft": False,
                    "variants": [
                        f"https://imagedelivery.net/hash/{cid}/public",
                        f"https://imagedelivery.net/hash/{cid}/thumbnail",
                    ],
                    "meta": {"origin": "mobile"},
                    "creator": "creator-99",
                },
            },
            status=200,
        )

        image = CloudflareImage.objects.register_uploaded(cid, user=user)

        assert image.pk is not None
        assert image.status == ImageUploadStatus.UPLOADED
        assert image.user == user
        assert image.filename == "photo.jpg"
        assert image.creator == "creator-99"
        assert image.cloudflare_metadata == {"origin": "mobile"}
        # CF "meta" is mirrored into the queryable metadata field.
        assert image.metadata == {"origin": "mobile"}
        assert len(image.variants) == 2
        assert image.public_url.endswith("/public")
        # Persisted and queryable, including by the mirrored metadata.
        assert CloudflareImage.objects.filter(cloudflare_id=cid).count() == 1
        assert CloudflareImage.objects.filter(metadata__origin="mobile").exists()

    @responses.activate
    def test_missing_image_raises_not_found_and_creates_no_row(self, user):
        cid = "does-not-exist"
        responses.add(
            responses.GET,
            _image_url(cid),
            json={
                "success": False,
                "errors": [{"code": 5404, "message": "Image not found"}],
                "messages": [],
                "result": None,
            },
            status=404,
        )

        with pytest.raises(ImageNotFoundError):
            CloudflareImage.objects.register_uploaded(cid, user=user)

        assert not CloudflareImage.objects.filter(cloudflare_id=cid).exists()

    @responses.activate
    def test_draft_image_raises_not_ready_and_creates_no_row(self, user):
        cid = "still-a-draft"
        responses.add(
            responses.GET,
            _image_url(cid),
            json={
                "success": True,
                "errors": [],
                "messages": [],
                "result": {
                    "id": cid,
                    "draft": True,
                    "variants": [],
                },
            },
            status=200,
        )

        with pytest.raises(ImageNotReadyError):
            CloudflareImage.objects.register_uploaded(cid, user=user)

        assert not CloudflareImage.objects.filter(cloudflare_id=cid).exists()
