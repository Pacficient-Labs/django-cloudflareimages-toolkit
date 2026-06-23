"""
Tests for self-healing image deletion (issue #27).

Deletion must converge on the desired end state ("image not in Cloudflare,
no local row") even across partial or duplicate deletes. A Cloudflare 404 on
delete means the image is already gone, which for the cleanup command, the
admin action, and the viewset delete is success — not an error to re-raise on
every subsequent run.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
import responses
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from django_cloudflareimages_toolkit.exceptions import (
    CloudflareImagesError,
    ImageNotFoundError,
)
from django_cloudflareimages_toolkit.models import CloudflareImage, ImageUploadStatus
from django_cloudflareimages_toolkit.services import cloudflare_service

API = "/cloudflare-images/api"
BASE = "https://api.cloudflare.com/client/v4"
ACCOUNT = "test-account-id"
User = get_user_model()


def _delete_url(cloudflare_id: str) -> str:
    return f"{BASE}/accounts/{ACCOUNT}/images/v1/{cloudflare_id}"


def make_image(cloudflare_id, user, status=ImageUploadStatus.UPLOADED, **kwargs):
    return CloudflareImage.objects.create(
        cloudflare_id=cloudflare_id,
        upload_url=f"https://upload.example/{cloudflare_id}",
        expires_at=timezone.now() + timedelta(minutes=30),
        user=user,
        status=status,
        **kwargs,
    )


def _mock_delete_404(cloudflare_id: str) -> None:
    """Cloudflare reports the image as already gone."""
    responses.add(
        responses.DELETE,
        _delete_url(cloudflare_id),
        json={
            "success": False,
            "errors": [{"code": 5404, "message": "Image not found"}],
            "result": None,
        },
        status=404,
    )


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pw")


# ---------------------------------------------------------------------------
# Service layer: missing_ok semantics
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDeleteImageMissingOk:
    @responses.activate
    def test_missing_ok_treats_404_as_success(self, user):
        image = make_image("cf-gone", user)
        _mock_delete_404("cf-gone")
        # No raise; the desired end state ("gone") is already true.
        assert cloudflare_service.delete_image(image, missing_ok=True) is True

    @responses.activate
    def test_404_raises_typed_not_found_by_default(self, user):
        image = make_image("cf-missing", user)
        _mock_delete_404("cf-missing")
        with pytest.raises(ImageNotFoundError):
            cloudflare_service.delete_image(image)

    @responses.activate
    def test_not_found_is_a_cloudflare_error_subclass(self, user):
        """Default 404 stays catchable by existing ``except CloudflareImagesError``."""
        image = make_image("cf-missing-2", user)
        _mock_delete_404("cf-missing-2")
        with pytest.raises(CloudflareImagesError):
            cloudflare_service.delete_image(image)


# ---------------------------------------------------------------------------
# Viewset delete converges
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestViewsetDeleteSelfHeals:
    @pytest.fixture
    def api(self, user):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=user)
        return client

    @responses.activate
    def test_destroy_removes_row_when_already_absent(self, api, user):
        image = make_image("cf-gone", user)  # unreferenced
        _mock_delete_404("cf-gone")
        resp = api.delete(f"{API}/images/{image.id}/")
        # Already gone in Cloudflare -> still a successful, converging delete.
        assert resp.status_code == 204
        assert not CloudflareImage.objects.filter(pk=image.pk).exists()


# ---------------------------------------------------------------------------
# Cleanup command converges
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOrphanCleanupSelfHeals:
    @responses.activate
    def test_cleanup_converges_on_already_absent_orphan(self, user):
        """Re-running cleanup after a partial failure converges.

        Models the "Cloudflare delete already happened on a previous run but
        the local row stuck" case: the row is present, Cloudflare returns 404,
        and the run must remove the row and count it as deleted (no repeated
        error), rather than looping on the same orphan forever.
        """
        image = make_image("orphan-1", user)  # UPLOADED, no usages
        # Age it past the default 30-day orphan retention window.
        CloudflareImage.objects.filter(pk=image.pk).update(
            created_at=timezone.now() - timedelta(days=60)
        )
        _mock_delete_404("orphan-1")

        out = StringIO()
        call_command("cleanup_expired_images", "--delete-orphans", stdout=out)

        output = out.getvalue()
        assert not CloudflareImage.objects.filter(pk=image.pk).exists()
        assert "Deleted 1 orphaned" in output
        assert "Failed to delete" not in output
