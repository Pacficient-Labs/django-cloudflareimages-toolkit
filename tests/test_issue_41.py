"""
Regression tests for issue #41.

1. ``thumbnail_url`` returned ``None`` on accounts without a named ``thumbnail``
   variant, so the admin never rendered a preview.
2. Images referenced through a plain ``ForeignKey``/``OneToOneField`` were never
   indexed in ``ImageUsage``, so the admin labelled every one "Orphaned".
3. A bare-string ``variants`` value made ``get_variant_url`` silently return
   ``None``.
"""

import importlib
import json
import uuid
from datetime import timedelta
from io import StringIO

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection, models
from django.db.models.signals import post_delete, pre_delete
from django.test import Client
from django.test.utils import isolate_apps
from django.urls import reverse
from django.utils import timezone

from django_cloudflareimages_toolkit.models import (
    CloudflareImage,
    ImageUploadLog,
    ImageUploadStatus,
    ImageUsage,
)
from django_cloudflareimages_toolkit.registry import (
    _is_image_reference,
    get_models_with_image_fields,
    record_usage,
    register_usage,
)

from .models import Banner, Content, Post, Product, Profile, Story

DELIVERY = "https://imagedelivery.net/test-account-hash"
CHANGELIST = "admin:django_cloudflareimages_toolkit_cloudflareimage_changelist"


def make_image(cloudflare_id, variants=None, **kwargs):
    return CloudflareImage.objects.create(
        cloudflare_id=cloudflare_id,
        upload_url=f"https://upload.example/{cloudflare_id}",
        expires_at=timezone.now() + timedelta(minutes=30),
        status=ImageUploadStatus.UPLOADED,
        variants=variants if variants is not None else [],
        **kwargs,
    )


def usages_for(obj):
    ct = ContentType.objects.get_for_model(type(obj))
    return ImageUsage.objects.filter(content_type=ct, object_id=str(obj.pk))


@pytest.fixture
def thumbnail_variant(settings):
    def _set(value):
        settings.CLOUDFLARE_IMAGES = {
            **settings.CLOUDFLARE_IMAGES,
            "THUMBNAIL_VARIANT": value,
        }

    return _set


@pytest.fixture
def admin_client(db):
    admin = get_user_model().objects.create_superuser("boss", "b@example.com", "pw")
    client = Client()
    client.force_login(admin)
    return client


# --- 1. thumbnail_url -------------------------------------------------------


class TestThumbnailUrl:
    def test_falls_back_to_public_when_no_thumbnail_variant(self):
        image = CloudflareImage(variants=[f"{DELIVERY}/cf-1/public"])
        assert image.thumbnail_url == f"{DELIVERY}/cf-1/public"

    def test_prefers_named_thumbnail_variant(self):
        image = CloudflareImage(
            variants=[f"{DELIVERY}/cf-1/public", f"{DELIVERY}/cf-1/thumbnail"]
        )
        assert image.thumbnail_url == f"{DELIVERY}/cf-1/thumbnail"

    def test_no_variants_returns_none(self):
        assert CloudflareImage(variants=[]).thumbnail_url is None

    def test_setting_names_a_custom_variant(self, thumbnail_variant):
        thumbnail_variant("small")
        image = CloudflareImage(
            variants=[f"{DELIVERY}/cf-1/public", f"{DELIVERY}/cf-1/small"]
        )
        assert image.thumbnail_url == f"{DELIVERY}/cf-1/small"

    def test_setting_with_options_builds_flexible_variant(self, thumbnail_variant):
        thumbnail_variant("w=150,h=150,fit=cover")
        image = CloudflareImage(variants=[f"{DELIVERY}/cf-1/public"])
        assert image.thumbnail_url == f"{DELIVERY}/cf-1/w=150,h=150,fit=cover"

    def test_flexible_setting_without_public_returns_none(self, thumbnail_variant):
        thumbnail_variant("w=150")
        assert CloudflareImage(variants=[]).thumbnail_url is None

    @pytest.mark.django_db
    def test_gallery_renders_preview(self, admin_client):
        make_image("cf-1", variants=[f"{DELIVERY}/cf-1/public"])
        resp = admin_client.get(reverse(CHANGELIST))
        assert resp.status_code == 200
        assert f'src="{DELIVERY}/cf-1/public"'.encode() in resp.content
        assert b"No preview" not in resp.content


# --- 2. FK / OneToOne references ---------------------------------------------


class TestRelationalDiscovery:
    def test_discovers_foreign_key_and_one_to_one(self):
        registry = get_models_with_image_fields(refresh=True)
        assert registry.get(Post) == ["image"]
        assert registry.get(Profile) == ["avatar"]

    @isolate_apps("tests")
    def test_fk_to_a_proxy_model_counts_as_a_reference(self):
        class ImageProxy(CloudflareImage):
            class Meta:
                proxy = True
                app_label = "tests"

        class Gallery(models.Model):
            cover = models.ForeignKey(ImageProxy, on_delete=models.CASCADE)

            class Meta:
                app_label = "tests"

        field = Gallery._meta.get_field("cover")
        assert _is_image_reference(field, CloudflareImage)

    @isolate_apps("tests")
    def test_mti_parent_link_is_not_a_reference(self):
        class SubImage(CloudflareImage):
            class Meta:
                app_label = "tests"

        field = SubImage._meta.get_field("cloudflareimage_ptr")
        assert not _is_image_reference(field, CloudflareImage)

    def test_skips_toolkit_bookkeeping_models(self):
        registry = get_models_with_image_fields(refresh=True)
        assert ImageUsage not in registry
        assert ImageUploadLog not in registry


@pytest.mark.django_db
class TestRelationalSync:
    def test_fk_save_creates_linked_usage(self):
        image = make_image("cf-1")
        post = Post.objects.create(image=image)
        usage = usages_for(post).get()
        assert (usage.field_name, usage.cloudflare_id) == ("image", "cf-1")
        assert usage.image == image

    def test_clearing_fk_removes_usage(self):
        post = Post.objects.create(image=make_image("cf-1"))
        post.image = None
        post.save()
        assert not usages_for(post).exists()

    def test_repointing_fk_updates_usage(self):
        post = Post.objects.create(image=make_image("cf-1"))
        post.image = make_image("cf-2")
        post.save()
        assert usages_for(post).get().cloudflare_id == "cf-2"

    def test_deleting_host_removes_usage(self):
        post = Post.objects.create(image=make_image("cf-1"))
        post.delete()
        assert not ImageUsage.objects.exists()

    def test_one_to_one_save_creates_usage(self):
        profile = Profile.objects.create(avatar=make_image("cf-1"))
        assert usages_for(profile).get().field_name == "avatar"

    def test_cascade_delete_of_image_removes_usage(self):
        image = make_image("cf-1")
        Profile.objects.create(avatar=image)
        image.delete()
        assert not Profile.objects.exists()
        assert not ImageUsage.objects.exists()

    def test_set_null_delete_of_image_leaves_no_stale_usage(self):
        image = make_image("cf-1")
        post = Post.objects.create(image=image)
        image.delete()
        post.refresh_from_db()
        assert post.image is None
        # No leftover "unregistered reference" that a re-upload under the same
        # id would be wrongly linked to.
        assert not ImageUsage.objects.exists()

    def test_deleting_image_keeps_other_references(self):
        image = make_image("cf-1")
        Post.objects.create(image=image)
        product = Product.objects.create(image="cf-1")
        image.delete()
        assert list(ImageUsage.objects.values_list("object_id", flat=True)) == [
            str(product.pk)
        ]

    def test_update_fields_without_fk_keeps_saved_reference(self):
        post = Post.objects.create(image=make_image("cf-1"))
        post.image = make_image("cf-2")
        post.save(update_fields=["title"])  # the FK column isn't written
        assert usages_for(post).get().cloudflare_id == "cf-1"

        post.save(update_fields=["image_id"])
        assert usages_for(post).get().cloudflare_id == "cf-2"

    @isolate_apps("tests")
    def test_delete_through_proxy_resyncs_hosts(self):
        from django_cloudflareimages_toolkit.signals import connect_image_receivers

        class ImageProxy(CloudflareImage):
            class Meta:
                proxy = True
                app_label = "tests"

        # apps.ready() does this for every proxy in the app registry.
        connect_image_receivers(ImageProxy)
        image = make_image("cf-1")
        post = Post.objects.create(image=image)
        proxied = ImageProxy.objects.get(pk=image.pk)
        # What the collector does for SET_NULL around a proxy delete: signals
        # name the proxy, the column is rewritten without post_save.
        pre_delete.send(sender=ImageProxy, instance=proxied, using="default")
        Post.objects.filter(pk=post.pk).update(image=None)
        post_delete.send(sender=ImageProxy, instance=proxied, using="default")
        assert not usages_for(post).exists()

    def test_delete_with_deferred_cloudflare_id(self):
        image = make_image("cf-1")
        post = Post.objects.create(image=image)
        CloudflareImage.objects.only("pk").get(pk=image.pk).delete()
        assert not CloudflareImage.objects.exists()
        assert not usages_for(post).exists()

    def test_unrelated_models_keep_fast_delete(self):
        # A sender-less delete receiver would make Django's collector skip
        # fast deletes and field deferral for every model in the project.
        from .models import Plain

        assert not pre_delete.has_listeners(Plain)
        assert not post_delete.has_listeners(Plain)

    def test_set_callable_delete_repoints_usage(self):
        fallback = make_image("cf-fallback")
        banner = Banner.objects.create(image=make_image("cf-1"))
        CloudflareImage.objects.get(cloudflare_id="cf-1").delete()
        banner.refresh_from_db()
        assert banner.image == fallback
        usage = usages_for(banner).get()
        assert (usage.cloudflare_id, usage.image) == ("cf-fallback", fallback)

    def test_save_keeps_manual_row_colliding_with_fk_name(self):
        # A pre-upgrade workaround: a manual row labelled with the FK's name.
        post = Post.objects.create()
        ct = ContentType.objects.get_for_model(Post)
        record_usage(ct, post.pk, "image", "cf-manual", source=ImageUsage.SOURCE_MANUAL)

        post.save()  # FK is null
        post.image = make_image("cf-1")
        post.save()

        usage = usages_for(post).get()
        assert (usage.cloudflare_id, usage.source) == (
            "cf-manual",
            ImageUsage.SOURCE_MANUAL,
        )

    def test_loaddata_with_forward_fk_reference(self, tmp_path):
        image_pk = str(uuid.uuid4())
        fixture = tmp_path / "fx.json"
        fixture.write_text(
            json.dumps(
                [
                    {"model": "tests.post", "pk": 1, "fields": {"image": image_pk}},
                    {
                        "model": "django_cloudflareimages_toolkit.cloudflareimage",
                        "pk": image_pk,
                        "fields": {
                            "cloudflare_id": "cf-fx",
                            "upload_url": "https://upload.example/cf-fx",
                            "expires_at": "2030-01-01T00:00:00Z",
                            "created_at": "2030-01-01T00:00:00Z",
                            "updated_at": "2030-01-01T00:00:00Z",
                        },
                    },
                ]
            )
        )
        call_command("loaddata", str(fixture), verbosity=0)
        call_command("reconcile_image_usage", stdout=StringIO())
        assert usages_for(Post.objects.get(pk=1)).get().cloudflare_id == "cf-fx"

    def test_register_usage_rejects_fk_field_name(self):
        post = Post.objects.create()
        with pytest.raises(ValueError):
            register_usage(post, "cf-x", field_name="image")


@pytest.mark.django_db
class TestRelationalReconcile:
    def test_reconcile_backfills_fk_references_written_without_signals(self):
        image = make_image("cf-1")
        post = Post.objects.create()
        Post.objects.filter(pk=post.pk).update(image=image)  # bypasses post_save
        assert not usages_for(post).exists()

        call_command("reconcile_image_usage", stdout=StringIO())

        usage = usages_for(post).get()
        assert (usage.cloudflare_id, usage.image) == ("cf-1", image)

    def test_reconcile_prunes_stale_fk_usage(self):
        post = Post.objects.create(image=make_image("cf-1"))
        Post.objects.filter(pk=post.pk).update(image=None)

        call_command("reconcile_image_usage", stdout=StringIO())

        assert not usages_for(post).exists()


@pytest.mark.django_db
class TestAdminUsage:
    def test_fk_referenced_image_is_not_orphaned(self, admin_client):
        Post.objects.create(image=make_image("cf-1"))
        resp = admin_client.get(reverse(CHANGELIST))
        assert b"Orphaned</span>" not in resp.content
        assert "Used ×1".encode() in resp.content or b"Used &times;1" in resp.content

    def test_orphaned_filter_excludes_fk_referenced(self, admin_client):
        Post.objects.create(image=make_image("cf-used"))
        make_image("cf-orphan")
        resp = admin_client.get(reverse(CHANGELIST), {"orphaned": "1", "view": "table"})
        assert b"cf-orphan" in resp.content
        assert b"cf-used" not in resp.content


@pytest.mark.django_db
class TestInheritedFk:
    """An FK inherited through multi-table inheritance is one physical column,
    so it must be one usage row, keyed to the model that declares it."""

    def test_discovered_on_declaring_model_only(self):
        registry = get_models_with_image_fields(refresh=True)
        assert registry.get(Content) == ["image"]
        assert Story not in registry

    def test_child_save_writes_one_row_on_parent(self):
        story = Story.objects.create(image=make_image("cf-1"))
        rows = ImageUsage.objects.all()
        assert [(r.content_type.model_class(), r.object_id) for r in rows] == [
            (Content, str(story.pk))
        ]

        story.image = make_image("cf-2")
        story.save()
        assert list(ImageUsage.objects.values_list("cloudflare_id", flat=True)) == [
            "cf-2"
        ]

    def test_reconcile_keeps_a_single_row(self):
        Story.objects.create(image=make_image("cf-1"))
        call_command("reconcile_image_usage", stdout=StringIO())
        assert ImageUsage.objects.count() == 1

    def test_deleting_child_removes_row(self):
        story = Story.objects.create(image=make_image("cf-1"))
        story.delete()
        assert not ImageUsage.objects.exists()


# --- 3. bare-string variants --------------------------------------------------


class TestStringVariants:
    def test_get_variant_url_accepts_bare_string(self):
        image = CloudflareImage(variants=f"{DELIVERY}/cf-1/public")
        assert image.public_url == f"{DELIVERY}/cf-1/public"

    @pytest.mark.django_db
    def test_save_stores_a_list(self):
        image = make_image("cf-1", variants=f"{DELIVERY}/cf-1/public")
        image.refresh_from_db()
        assert image.variants == [f"{DELIVERY}/cf-1/public"]

    @pytest.mark.django_db
    def test_cloudflare_response_with_string_stores_a_list(self):
        image = make_image("cf-1")
        image.update_from_cloudflare_response({"variants": f"{DELIVERY}/cf-1/public"})
        image.refresh_from_db()
        assert image.variants == [f"{DELIVERY}/cf-1/public"]

    @pytest.mark.django_db
    def test_data_migration_wraps_existing_strings(self):
        bad = make_image("cf-bad")
        good = make_image("cf-good", variants=[f"{DELIVERY}/cf-good/public"])
        empty = make_image("cf-empty")
        # Write the bad shape directly, the way it got into production.
        CloudflareImage.objects.filter(pk=bad.pk).update(
            variants=f"{DELIVERY}/cf-bad/public"
        )
        CloudflareImage.objects.filter(pk=empty.pk).update(variants="")

        migration = importlib.import_module(
            "django_cloudflareimages_toolkit.migrations.0008_wrap_string_variants"
        )
        migration.wrap_string_variants(django_apps, connection.schema_editor())

        for obj, expected in [
            (bad, [f"{DELIVERY}/cf-bad/public"]),
            (good, [f"{DELIVERY}/cf-good/public"]),
            (empty, []),
        ]:
            obj.refresh_from_db()
            assert obj.variants == expected
