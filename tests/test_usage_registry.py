"""
Tests for the image usage registry: discovery, signals, manual API, reconcile,
orphan detection, idempotency, and the opt-in orphan cleanup.
"""

from datetime import timedelta

import pytest
import responses
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.utils import timezone

from django_cloudflareimages_toolkit.models import (
    CloudflareImage,
    ImageUploadStatus,
    ImageUsage,
)
from django_cloudflareimages_toolkit.registry import (
    get_models_with_image_fields,
    register_usage,
    unregister_usage,
)

from .models import Article, Plain, Product

BASE = "https://api.cloudflare.com/client/v4"
ACCOUNT = "test-account-id"


def make_image(cloudflare_id, user=None, status=ImageUploadStatus.UPLOADED):
    return CloudflareImage.objects.create(
        cloudflare_id=cloudflare_id,
        upload_url=f"https://upload.example/{cloudflare_id}",
        expires_at=timezone.now() + timedelta(minutes=30),
        user=user,
        status=status,
    )


def usages_for(obj):
    ct = ContentType.objects.get_for_model(type(obj))
    return ImageUsage.objects.filter(content_type=ct, object_id=str(obj.pk))


def _mock_delete(cloudflare_id):
    responses.add(
        responses.DELETE,
        f"{BASE}/accounts/{ACCOUNT}/images/v1/{cloudflare_id}",
        json={"success": True, "result": {}},
        status=200,
    )


class TestRegistryDiscovery:
    def test_discovers_image_fields_and_ignores_others(self):
        registry = get_models_with_image_fields(refresh=True)
        assert registry.get(Product) == ["image"]
        # Multiple fields are returned in a stable, sorted order.
        assert registry.get(Article) == ["cover", "thumbnail"]
        assert Plain not in registry


@pytest.mark.django_db
class TestSignalSync:
    def test_save_creates_usage(self):
        product = Product.objects.create(name="p", image="cf-1")
        usage = usages_for(product).get()
        assert usage.field_name == "image"
        assert usage.cloudflare_id == "cf-1"

    def test_usage_links_to_existing_image(self):
        make_image("cf-1")
        product = Product.objects.create(image="cf-1")
        assert usages_for(product).get().image is not None

    def test_clearing_field_removes_usage(self):
        product = Product.objects.create(image="cf-1")
        assert usages_for(product).count() == 1
        product.image = None
        product.save()
        assert usages_for(product).count() == 0

    def test_changing_field_updates_usage(self):
        product = Product.objects.create(image="cf-1")
        product.image = "cf-2"
        product.save()
        usage = usages_for(product).get()
        assert usage.cloudflare_id == "cf-2"

    def test_deleting_object_removes_usages(self):
        product = Product.objects.create(image="cf-1")
        product.delete()
        assert ImageUsage.objects.count() == 0

    def test_multiple_fields_and_uuid_pk(self):
        article = Article.objects.create(cover="cf-cover", thumbnail="cf-thumb")
        fields = set(usages_for(article).values_list("field_name", flat=True))
        assert fields == {"cover", "thumbnail"}

    def test_plain_model_creates_no_usage(self):
        Plain.objects.create(name="x")
        assert ImageUsage.objects.count() == 0

    def test_unregistered_then_linked_on_image_save(self):
        product = Product.objects.create(image="cf-late")
        usage = usages_for(product).get()
        assert usage.image is None
        assert usage.is_unregistered is True
        # Registering the image backfills the link.
        image = make_image("cf-late")
        usage.refresh_from_db()
        assert usage.image_id == image.pk


@pytest.mark.django_db
class TestManualApi:
    def test_register_and_unregister(self):
        plain = Plain.objects.create(name="x")
        register_usage(plain, "cf-manual")
        usage = usages_for(plain).get()
        assert usage.field_name == "manual"
        assert usage.cloudflare_id == "cf-manual"

        unregister_usage(plain)
        assert usages_for(plain).count() == 0

    def test_register_is_idempotent(self):
        plain = Plain.objects.create(name="x")
        register_usage(plain, "cf-manual")
        register_usage(plain, "cf-manual")
        assert usages_for(plain).count() == 1


@pytest.mark.django_db
class TestReconcile:
    def test_rebuilds_after_signal_bypass(self):
        # bulk_create / update bypass signals -> no usage row yet.
        Product.objects.bulk_create([Product(image="cf-bulk")])
        assert ImageUsage.objects.count() == 0

        call_command("reconcile_image_usage")
        assert ImageUsage.objects.filter(cloudflare_id="cf-bulk").count() == 1

    def test_prunes_stale_auto_rows(self):
        product = Product.objects.create(image="cf-1")
        assert ImageUsage.objects.count() == 1
        # QuerySet.update() bypasses the post_save signal, so the usage row is
        # left pointing at an image the object no longer references.
        Product.objects.filter(pk=product.pk).update(image=None)
        assert ImageUsage.objects.count() == 1

        call_command("reconcile_image_usage")
        assert ImageUsage.objects.count() == 0

    def test_manual_usage_survives_reconcile(self):
        product = Product.objects.create(image="cf-1")
        register_usage(product, "cf-manual")  # field_name="manual"
        assert usages_for(product).count() == 2

        call_command("reconcile_image_usage")
        fields = set(usages_for(product).values_list("field_name", flat=True))
        assert fields == {"image", "manual"}

    def test_dry_run_writes_nothing(self):
        Product.objects.bulk_create([Product(image="cf-bulk")])
        call_command("reconcile_image_usage", "--dry-run")
        assert ImageUsage.objects.count() == 0

    def test_idempotent_and_deterministic(self):
        Product.objects.create(image="cf-1")
        Article.objects.create(cover="cf-2", thumbnail="cf-3")

        def snapshot():
            return sorted(
                ImageUsage.objects.values_list(
                    "object_id", "field_name", "cloudflare_id"
                )
            )

        call_command("reconcile_image_usage")
        first = snapshot()
        call_command("reconcile_image_usage")
        second = snapshot()

        assert first == second
        # No duplicate rows created on the second pass.
        assert ImageUsage.objects.count() == len(first)


@pytest.mark.django_db
class TestOrphanDetection:
    def test_orphan_query(self):
        used = make_image("cf-used")
        make_image("cf-orphan")
        Product.objects.create(image="cf-used")

        orphans = CloudflareImage.objects.filter(usages__isnull=True)
        assert list(orphans.values_list("cloudflare_id", flat=True)) == ["cf-orphan"]
        assert used.usages.count() == 1

    @responses.activate
    def test_cleanup_delete_orphans(self):
        make_image("cf-orphan")  # uploaded, created_at = now
        _mock_delete("cf-orphan")

        # Too new to be deleted with the default 30-day threshold.
        call_command("cleanup_expired_images", "--delete-orphans")
        assert CloudflareImage.objects.filter(cloudflare_id="cf-orphan").exists()

        # With orphan-days=0 the orphan is eligible and gets deleted.
        call_command("cleanup_expired_images", "--delete-orphans", "--orphan-days", "0")
        assert not CloudflareImage.objects.filter(cloudflare_id="cf-orphan").exists()

    @responses.activate
    def test_cleanup_skips_referenced_images(self):
        make_image("cf-used")
        Product.objects.create(image="cf-used")

        call_command("cleanup_expired_images", "--delete-orphans", "--orphan-days", "0")
        assert CloudflareImage.objects.filter(cloudflare_id="cf-used").exists()
