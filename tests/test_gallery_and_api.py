"""
Tests for the admin gallery and the REST API additions (usages, orphans,
cloudflare_id lookup, search/filter, usage-aware delete, bulk delete).
"""

import uuid
from datetime import timedelta

import pytest
import responses
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from django_cloudflareimages_toolkit.models import CloudflareImage, ImageUploadStatus

from .models import Product

API = "/cloudflare-images/api"
BASE = "https://api.cloudflare.com/client/v4"
ACCOUNT = "test-account-id"
User = get_user_model()


def make_image(cloudflare_id, user, status=ImageUploadStatus.UPLOADED, **kwargs):
    return CloudflareImage.objects.create(
        cloudflare_id=cloudflare_id,
        upload_url=f"https://upload.example/{cloudflare_id}",
        expires_at=timezone.now() + timedelta(minutes=30),
        user=user,
        status=status,
        **kwargs,
    )


def _mock_delete(cloudflare_id):
    responses.add(
        responses.DELETE,
        f"{BASE}/accounts/{ACCOUNT}/images/v1/{cloudflare_id}",
        json={"success": True, "result": {}},
        status=200,
    )


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pw")


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestApiLookup:
    def test_lookup_by_cloudflare_id(self, api, user):
        make_image("cf-1", user)
        resp = api.get(f"{API}/images/by-cloudflare-id/cf-1/")
        assert resp.status_code == 200
        assert resp.data["cloudflare_id"] == "cf-1"

    def test_lookup_by_cloudflare_id_404(self, api, user):
        resp = api.get(f"{API}/images/by-cloudflare-id/nope/")
        assert resp.status_code == 404

    def test_filter_by_filename(self, api, user):
        make_image("cf-1", user, filename="invoice.png")
        make_image("cf-2", user, filename="avatar.jpg")
        resp = api.get(f"{API}/images/", {"filename": "invoice"})
        ids = [row["cloudflare_id"] for row in resp.data["results"]]
        assert ids == ["cf-1"]

    def test_filter_by_creator(self, api, user):
        make_image("cf-1", user, creator="team-a")
        make_image("cf-2", user, creator="team-b")
        resp = api.get(f"{API}/images/", {"creator": "team-a"})
        ids = [row["cloudflare_id"] for row in resp.data["results"]]
        assert ids == ["cf-1"]

    def test_filter_orphaned(self, api, user):
        make_image("cf-orphan", user)
        make_image("cf-used", user)
        Product.objects.create(image="cf-used")
        resp = api.get(f"{API}/images/", {"orphaned": "true"})
        ids = [row["cloudflare_id"] for row in resp.data["results"]]
        assert ids == ["cf-orphan"]


@pytest.mark.django_db
class TestApiUsages:
    def test_image_usages_action(self, api, user):
        image = make_image("cf-1", user)
        Product.objects.create(image="cf-1")
        resp = api.get(f"{API}/images/{image.id}/usages/")
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["field_name"] == "image"

    def test_orphans_endpoint(self, api, user):
        make_image("cf-orphan", user)
        make_image("cf-used", user)
        Product.objects.create(image="cf-used")
        resp = api.get(f"{API}/images/orphans/")
        ids = [row["cloudflare_id"] for row in resp.data["results"]]
        assert ids == ["cf-orphan"]

    def test_usages_viewset(self, api, user):
        make_image("cf-1", user)
        Product.objects.create(image="cf-1")
        resp = api.get(f"{API}/usages/")
        assert resp.status_code == 200
        assert resp.data["count"] == 1


@pytest.mark.django_db
class TestApiDelete:
    @responses.activate
    def test_destroy_blocked_while_referenced(self, api, user):
        image = make_image("cf-1", user)
        Product.objects.create(image="cf-1")
        resp = api.delete(f"{API}/images/{image.id}/")
        assert resp.status_code == 409
        assert "usages" in resp.data
        assert CloudflareImage.objects.filter(pk=image.pk).exists()

    @responses.activate
    def test_destroy_with_force(self, api, user):
        image = make_image("cf-1", user)
        Product.objects.create(image="cf-1")
        _mock_delete("cf-1")
        resp = api.delete(f"{API}/images/{image.id}/?force=true")
        assert resp.status_code == 204
        assert not CloudflareImage.objects.filter(pk=image.pk).exists()

    @responses.activate
    def test_destroy_unreferenced(self, api, user):
        image = make_image("cf-1", user)
        _mock_delete("cf-1")
        resp = api.delete(f"{API}/images/{image.id}/")
        assert resp.status_code == 204
        assert not CloudflareImage.objects.filter(pk=image.pk).exists()

    @responses.activate
    def test_bulk_delete_mixed_results(self, api, user):
        keep = make_image("cf-keep", user)
        gone = make_image("cf-gone", user)
        Product.objects.create(image="cf-keep")  # referenced -> in_use
        _mock_delete("cf-gone")

        missing_id = str(uuid.uuid4())
        resp = api.post(
            f"{API}/images/bulk_delete/",
            {"ids": [str(keep.id), str(gone.id), missing_id]},
            format="json",
        )
        assert resp.status_code == 200
        by_status = {}
        for row in resp.data["results"]:
            by_status.setdefault(row["status"], []).append(row)

        assert {r["id"] for r in by_status["in_use"]} == {str(keep.id)}
        assert {r["id"] for r in by_status["deleted"]} == {str(gone.id)}
        assert {r["id"] for r in by_status["not_found"]} == {missing_id}
        assert CloudflareImage.objects.filter(pk=keep.pk).exists()
        assert not CloudflareImage.objects.filter(pk=gone.pk).exists()

    @responses.activate
    def test_bulk_delete_by_cloudflare_id_with_force(self, api, user):
        image = make_image("cf-1", user)
        Product.objects.create(image="cf-1")
        _mock_delete("cf-1")
        resp = api.post(
            f"{API}/images/bulk_delete/",
            {"cloudflare_ids": ["cf-1"], "force": True},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["results"][0]["status"] == "deleted"
        assert not CloudflareImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
class TestAdminGallery:
    @pytest.fixture
    def admin_client(self, db):
        admin = User.objects.create_superuser("boss", "boss@example.com", "pw")
        client = Client()
        client.force_login(admin)
        return client

    def test_gallery_changelist_renders(self, admin_client, user):
        make_image("cf-1", user, filename="pic.png")
        url = reverse(
            "admin:django_cloudflareimages_toolkit_cloudflareimage_changelist"
        )
        resp = admin_client.get(url)
        assert resp.status_code == 200
        assert b"cfimg-gallery" in resp.content

    def test_table_view_toggle(self, admin_client, user):
        make_image("cf-1", user)
        url = reverse(
            "admin:django_cloudflareimages_toolkit_cloudflareimage_changelist"
        )
        resp = admin_client.get(url, {"view": "table"})
        assert resp.status_code == 200

    def test_orphaned_filter(self, admin_client, user):
        make_image("cf-orphan", user)
        url = reverse(
            "admin:django_cloudflareimages_toolkit_cloudflareimage_changelist"
        )
        resp = admin_client.get(url, {"orphaned": "1"})
        assert resp.status_code == 200

    def test_imageusage_admin_renders(self, admin_client, user):
        make_image("cf-1", user)
        Product.objects.create(image="cf-1")
        url = reverse("admin:django_cloudflareimages_toolkit_imageusage_changelist")
        resp = admin_client.get(url)
        assert resp.status_code == 200

    def test_imageusage_unregistered_filter(self, admin_client, user):
        Product.objects.create(image="cf-no-record")  # unregistered reference
        url = reverse("admin:django_cloudflareimages_toolkit_imageusage_changelist")
        resp = admin_client.get(url, {"unregistered": "1"})
        assert resp.status_code == 200
        assert b"cf-no-record" in resp.content

    def test_imageusage_admin_blocks_deletion(self, admin_client, user):
        # Codex finding #6: the registry admin must not let staff delete rows
        # (which would silently make still-referenced images look orphaned).
        make_image("cf-1", user)
        Product.objects.create(image="cf-1")
        from django_cloudflareimages_toolkit.models import ImageUsage

        usage = ImageUsage.objects.get()

        # Default delete-selected action must not be available.
        list_url = reverse(
            "admin:django_cloudflareimages_toolkit_imageusage_changelist"
        )
        list_resp = admin_client.get(list_url)
        assert b'<option value="delete_selected"' not in list_resp.content

        # Direct delete view must be refused.
        delete_url = reverse(
            "admin:django_cloudflareimages_toolkit_imageusage_delete",
            args=[usage.pk],
        )
        resp = admin_client.get(delete_url)
        assert resp.status_code in (302, 403)  # admin redirects forbidden views
        assert ImageUsage.objects.filter(pk=usage.pk).exists()


@pytest.mark.django_db
class TestApiLookupExtras:
    """Codex findings #3 (path-style ids) and #4 (metadata filter safety)."""

    def test_lookup_by_path_style_cloudflare_id(self, api, user):
        # Cloudflare custom IDs can contain slashes (e.g. ``products/123/hero``).
        # The lookup route must accept them; otherwise such images would be
        # unreachable through this endpoint.
        make_image("products/123/hero", user)
        resp = api.get(f"{API}/images/by-cloudflare-id/products/123/hero/")
        assert resp.status_code == 200
        assert resp.data["cloudflare_id"] == "products/123/hero"

    def test_metadata_filter_rejects_reserved_lookup(self, api, user):
        # ``metadata__contains=x`` would otherwise invoke the JSON ``contains``
        # lookup (unsupported on SQLite → 500). It must be quietly ignored.
        make_image("cf-1", user)
        resp = api.get(f"{API}/images/", {"metadata__contains": "anything"})
        assert resp.status_code == 200
        # Filter was ignored; the image still shows up.
        ids = [row["cloudflare_id"] for row in resp.data["results"]]
        assert ids == ["cf-1"]

    def test_metadata_filter_accepts_simple_key(self, api, user):
        make_image("cf-a", user, metadata={"kind": "avatar"})
        make_image("cf-b", user, metadata={"kind": "banner"})
        resp = api.get(f"{API}/images/", {"metadata__kind": "avatar"})
        assert resp.status_code == 200
        ids = [row["cloudflare_id"] for row in resp.data["results"]]
        assert ids == ["cf-a"]
