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

    def test_manual_owner_delete_clears_usage(self):
        # Plain has no CloudflareImageField, so its delete cleanup is wired by
        # register_usage rather than apps.ready().
        plain = Plain.objects.create(name="x")
        register_usage(plain, "cf-manual")
        assert usages_for(plain).count() == 1
        plain.delete()
        assert usages_for(plain).count() == 0


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

    def test_dry_run_count_matches_real_run_with_overlap(self):
        # A row that is BOTH stale (main loop: object_id has no current value)
        # and dangling (its owner no longer exists) must be counted once, so
        # dry-run and the real run report the same delete total. Codex PR #20.
        ct = ContentType.objects.get_for_model(Product)
        ImageUsage.objects.create(
            content_type=ct,
            object_id="424242",  # no such Product -> dangling
            field_name="image",  # a tracked field -> also "stale" in main loop
            cloudflare_id="cf-ghost",
            source=ImageUsage.SOURCE_AUTO,
        )

        dry = _call_with_output("reconcile_image_usage", "--dry-run")
        assert "remove 1 stale row(s)" in dry
        assert ImageUsage.objects.count() == 1  # dry-run didn't touch it

        real = _call_with_output("reconcile_image_usage")
        assert "remove 1 stale row(s)" in real
        assert ImageUsage.objects.count() == 0

    def test_prunes_dangling_rows(self):
        # A usage row whose owning object no longer exists (e.g. owner deleted
        # via a signal-bypassing path) is pruned by reconcile.
        ct = ContentType.objects.get_for_model(Plain)
        ImageUsage.objects.create(
            content_type=ct,
            object_id="999999",
            field_name="manual",
            cloudflare_id="cf-x",
        )
        assert ImageUsage.objects.count() == 1
        call_command("reconcile_image_usage")
        assert ImageUsage.objects.count() == 0

    def test_reconcile_prunes_undiscovered_field_rows(self):
        # A row created against a now-renamed/removed CloudflareImageField is
        # pruned (its (content_type, field_name) pair isn't in the registry),
        # while a manual row on the same object survives.
        product = Product.objects.create(image="cf-current")
        ct = ContentType.objects.get_for_model(Product)
        ImageUsage.objects.create(
            content_type=ct,
            object_id=str(product.pk),
            field_name="obsolete_field",
            cloudflare_id="cf-obsolete",
        )
        ImageUsage.objects.create(
            content_type=ct,
            object_id=str(product.pk),
            field_name="manual",
            cloudflare_id="cf-manual",
        )

        call_command("reconcile_image_usage")

        fields = set(usages_for(product).values_list("field_name", flat=True))
        # "image" (current discovered field) + "manual" (preserved) remain;
        # "obsolete_field" is dropped.
        assert fields == {"image", "manual"}

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


@pytest.mark.django_db(databases=["default", "other"])
class TestMultiDatabase:
    def test_signal_records_on_non_default_db(self):
        # Saving on "other" must record the ImageUsage row on "other" only.
        product = Product(image="cf-multidb")
        product.save(using="other")

        assert (
            ImageUsage.objects.using("other").filter(cloudflare_id="cf-multidb").count()
            == 1
        )
        assert (
            ImageUsage.objects.using("default")
            .filter(cloudflare_id="cf-multidb")
            .count()
            == 0
        )

    def test_delete_clears_on_correct_db(self):
        product = Product(image="cf-multidb")
        product.save(using="other")
        assert ImageUsage.objects.using("other").count() == 1

        product.delete(using="other")
        assert ImageUsage.objects.using("other").count() == 0


@pytest.mark.django_db
class TestSourceMarker:
    """Custom-label manual rows must survive reconcile (Codex finding #1)."""

    def test_manual_row_with_custom_label_survives_reconcile(self):
        # Plain has no CloudflareImageField, so ("Plain", "hero") will never
        # be in the discovered registry. Without a source marker, reconcile
        # would prune this row and silently lose the reference.
        plain = Plain.objects.create(name="x")
        register_usage(plain, "cf-custom", field_name="hero")
        usage = usages_for(plain).get()
        assert usage.source == ImageUsage.SOURCE_MANUAL
        assert usage.field_name == "hero"

        call_command("reconcile_image_usage")
        usage.refresh_from_db()
        assert usages_for(plain).count() == 1
        assert usage.cloudflare_id == "cf-custom"

    def test_auto_row_with_undiscovered_field_is_pruned(self):
        # A bare ImageUsage row created with the default source="auto" but
        # whose (content_type, field_name) is not in the discovered registry
        # *should* be pruned (it represents a removed/renamed field).
        product = Product.objects.create(image="cf-1")
        ct = ContentType.objects.get_for_model(Product)
        ImageUsage.objects.create(
            content_type=ct,
            object_id=str(product.pk),
            field_name="obsolete_field",
            cloudflare_id="cf-obsolete",
        )
        assert usages_for(product).count() == 2

        call_command("reconcile_image_usage")
        names = set(usages_for(product).values_list("field_name", flat=True))
        assert names == {"image"}

    def test_legacy_manual_label_still_protected(self):
        # Pre-migration manual rows defaulted to ``source="auto"`` (the new
        # column wasn't there) but always carried ``field_name="manual"``.
        # The MANUAL_FIELD_NAME exclusion still protects them.
        plain = Plain.objects.create(name="x")
        ct = ContentType.objects.get_for_model(Plain)
        ImageUsage.objects.create(
            content_type=ct,
            object_id=str(plain.pk),
            field_name="manual",
            cloudflare_id="cf-legacy",
            source=ImageUsage.SOURCE_AUTO,  # simulates pre-migration row
        )
        call_command("reconcile_image_usage")
        assert usages_for(plain).count() == 1


@pytest.mark.django_db
class TestLegacyMigration:
    """Migration 0005 protects legacy custom-label manual rows (Codex PR #20)."""

    def test_reclassifies_legacy_manual_rows(self):
        from importlib import import_module
        from types import SimpleNamespace

        from django.apps import apps as global_apps

        migration = import_module(
            "django_cloudflareimages_toolkit.migrations."
            "0005_backfill_last_referenced_at"
        )

        # A legacy custom-label manual row: created via register_usage(...,
        # field_name="hero") before the source column existed, so it defaulted
        # to "auto" and its field isn't a tracked CloudflareImageField.
        plain = Plain.objects.create(name="x")
        ct = ContentType.objects.get_for_model(Plain)
        legacy = ImageUsage.objects.create(
            content_type=ct,
            object_id=str(plain.pk),
            field_name="hero",
            cloudflare_id="cf-legacy",
            source=ImageUsage.SOURCE_AUTO,
        )
        # A genuine auto row for a tracked field must stay "auto".
        product = Product.objects.create(image="cf-auto")

        editor = SimpleNamespace(connection=SimpleNamespace(alias="default"))
        migration.backfill_registry_bookkeeping(global_apps, editor)

        legacy.refresh_from_db()
        assert legacy.source == ImageUsage.SOURCE_MANUAL

        auto_row = ImageUsage.objects.get(object_id=str(product.pk), field_name="image")
        assert auto_row.source == ImageUsage.SOURCE_AUTO

        # And the reclassified legacy row now survives reconcile.
        call_command("reconcile_image_usage")
        assert ImageUsage.objects.filter(pk=legacy.pk).exists()


@pytest.mark.django_db
class TestDryRunCounting:
    """``--dry-run`` must report what a real run would prune (Codex finding #2)."""

    def test_dry_run_counts_dangling_prune(self):
        ct = ContentType.objects.get_for_model(Plain)
        ImageUsage.objects.create(
            content_type=ct,
            object_id="999",
            field_name="manual",
            cloudflare_id="cf-dangling",
            source=ImageUsage.SOURCE_MANUAL,
        )
        # The row is dangling: its owning Plain pk=999 doesn't exist.

        out = _call_with_output("reconcile_image_usage", "--dry-run")
        assert "remove 1 stale row(s)" in out
        # Dry-run leaves the row in place.
        assert ImageUsage.objects.count() == 1

    def test_dry_run_counts_undiscovered_field_prune(self):
        product = Product.objects.create(image="cf-1")
        ct = ContentType.objects.get_for_model(Product)
        ImageUsage.objects.create(
            content_type=ct,
            object_id=str(product.pk),
            field_name="renamed_field",
            cloudflare_id="cf-renamed",
            source=ImageUsage.SOURCE_AUTO,
        )

        out = _call_with_output("reconcile_image_usage", "--dry-run")
        # 1 row removed for the renamed-field prune.
        assert "remove 1 stale row(s)" in out
        # All rows still present after dry-run.
        assert ImageUsage.objects.count() == 2


def _call_with_output(*args):
    """Run a management command and return its stdout as a string."""
    from io import StringIO

    buf = StringIO()
    call_command(*args, stdout=buf)
    return buf.getvalue()


@pytest.mark.django_db
class TestOrphanRetention:
    """Orphan retention uses ``last_referenced_at`` (Codex finding #5)."""

    @responses.activate
    def test_recently_unused_image_is_protected(self):
        # An old image that was referenced until just now should NOT be deleted
        # by an orphan-cleanup run, even though created_at is past the threshold.
        image = make_image("cf-protected")
        product = Product.objects.create(image="cf-protected")
        # Make created_at very old so the legacy clock would say "delete me".
        CloudflareImage.objects.filter(pk=image.pk).update(
            created_at=timezone.now() - timedelta(days=365)
        )
        # Now drop the reference (last_referenced_at remains "just now").
        product.delete()
        assert (
            CloudflareImage.objects.filter(cloudflare_id="cf-protected")
            .first()
            .last_referenced_at
            is not None
        )

        call_command(
            "cleanup_expired_images", "--delete-orphans", "--orphan-days", "30"
        )
        assert CloudflareImage.objects.filter(cloudflare_id="cf-protected").exists()

    @responses.activate
    def test_never_referenced_image_uses_created_at(self):
        # Backward compat: an image that has never been touched by the registry
        # (``last_referenced_at IS NULL``) falls back to ``created_at``.
        image = make_image("cf-never-used")
        CloudflareImage.objects.filter(pk=image.pk).update(
            created_at=timezone.now() - timedelta(days=365)
        )
        _mock_delete("cf-never-used")

        call_command(
            "cleanup_expired_images", "--delete-orphans", "--orphan-days", "30"
        )
        assert not CloudflareImage.objects.filter(
            cloudflare_id="cf-never-used"
        ).exists()


@pytest.mark.django_db
class TestLastReferencedBookkeeping:
    """``last_referenced_at`` is maintained on every reference change."""

    def test_post_delete_bumps_last_referenced(self):
        # Codex finding (PR #20): a usage row deletion is the moment the image
        # lost a reference. ``last_referenced_at`` must be updated then so
        # legacy data (created_at very old, last_referenced_at NULL until just
        # now) is no longer at risk of immediate orphan cleanup.
        image = make_image("cf-tracked")
        product = Product.objects.create(image="cf-tracked")
        bumped_at = CloudflareImage.objects.get(pk=image.pk).last_referenced_at
        assert bumped_at is not None

        # Bypass auto signals -> use the raw ORM to delete the usage row.
        ImageUsage.objects.filter(cloudflare_id="cf-tracked").delete()

        image.refresh_from_db()
        # Bumped again on the deletion event -> >= the value at creation time.
        assert image.last_referenced_at >= bumped_at
        # Reset the host record so we don't double-write.
        product.delete()

    def test_record_usage_bumps_previous_image_on_change(self):
        # When a host model's field value changes, the OLD image (which is
        # losing its reference) gets its ``last_referenced_at`` bumped too,
        # so its orphan retention clock starts now.
        old = make_image("cf-old")
        new = make_image("cf-new")
        product = Product.objects.create(image="cf-old")
        # Both should now have last_referenced_at set.
        old_bumped = CloudflareImage.objects.get(pk=old.pk).last_referenced_at
        assert old_bumped is not None

        # Reassign the field; sync_object will call record_usage with cf-new.
        product.image = "cf-new"
        product.save()

        old.refresh_from_db()
        new.refresh_from_db()
        # Old image's clock is bumped to mark the dereference moment.
        assert old.last_referenced_at >= old_bumped
        # New image is also referenced now.
        assert new.last_referenced_at is not None


@pytest.mark.django_db
class TestManualLabelCollision:
    """register_usage rejects labels that collide with a tracked field."""

    def test_register_usage_rejects_tracked_field_label(self):
        # Codex finding (PR #20): usage rows are unique on
        # (content_type, object_id, field_name), so a manual row whose label
        # matches a tracked CloudflareImageField would share the auto row's
        # slot and the two references would clobber each other. The collision
        # is rejected up front instead.
        product = Product.objects.create(name="p")  # image is blank
        with pytest.raises(ValueError, match="collides with the tracked"):
            register_usage(product, "cf-manual-collide", field_name="image")
        # Nothing was written for the colliding label.
        assert not ImageUsage.objects.filter(
            object_id=str(product.pk), field_name="image"
        ).exists()

    def test_distinct_manual_label_coexists_with_tracked_field(self):
        # A non-colliding manual label lives alongside the auto-tracked row and
        # both survive reconcile.
        product = Product.objects.create(image="cf-auto")
        register_usage(product, "cf-manual", field_name="gallery")
        assert usages_for(product).count() == 2

        call_command("reconcile_image_usage")

        rows = {u.field_name: u for u in usages_for(product)}
        assert rows["image"].source == ImageUsage.SOURCE_AUTO
        assert rows["image"].cloudflare_id == "cf-auto"
        assert rows["gallery"].source == ImageUsage.SOURCE_MANUAL
        assert rows["gallery"].cloudflare_id == "cf-manual"
