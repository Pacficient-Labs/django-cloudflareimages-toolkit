"""Backfill ``CloudflareImage.last_referenced_at`` for existing references.

Without this, upgrades that already have ``ImageUsage`` rows leave every
``last_referenced_at`` as ``NULL``. The orphan-retention fallback then uses
``created_at``, so a long-lived image whose final reference is removed shortly
after the upgrade could be deleted immediately by ``cleanup_expired_images
--delete-orphans``. Marking images that currently have a reference as
"referenced now" starts their retention clock at the upgrade moment.

Note on ``ImageUsage.source``: this migration deliberately does **not** try to
infer ``source`` for pre-existing rows. Before the ``source`` column existed
there is no stored signal that distinguishes a custom-label manual row
(``register_usage(obj, ..., field_name="hero")``) from an auto row for a
``CloudflareImageField`` that was later renamed/removed — both simply have a
``field_name`` that is not currently discovered. Guessing either way is wrong
for the other case (mark-manual would keep removed-field rows in-use forever;
mark-auto would prune real manual references). The ``source`` marker is
therefore authoritative only for rows created on/after this release by
``register_usage`` (which stamps ``"manual"``). The whole registry —
``ImageUsage`` table and the manual API — ships in this same unreleased batch,
so a real upgrade from the last release has no rows to classify. If you used
``register_usage`` with a custom ``field_name`` on an intermediate dev build,
re-run those ``register_usage`` calls after upgrading to stamp ``source`` (the
explicit preservation path); the default ``"manual"`` label is unaffected
because reconcile already protects ``field_name == MANUAL_FIELD_NAME``.
"""

from django.db import migrations


def backfill_last_referenced(apps, schema_editor):
    CloudflareImage = apps.get_model(
        "django_cloudflareimages_toolkit", "CloudflareImage"
    )
    ImageUsage = apps.get_model("django_cloudflareimages_toolkit", "ImageUsage")

    from django.utils import timezone

    db = schema_editor.connection.alias
    referenced_ids = list(
        ImageUsage.objects.using(db)
        .filter(image__isnull=False)
        .values_list("image_id", flat=True)
        .distinct()
    )
    if not referenced_ids:
        return
    CloudflareImage.objects.using(db).filter(
        pk__in=referenced_ids,
        last_referenced_at__isnull=True,
    ).update(last_referenced_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [
        (
            "django_cloudflareimages_toolkit",
            "0004_imageusage_source_and_image_last_referenced",
        ),
    ]

    operations = [
        migrations.RunPython(backfill_last_referenced, migrations.RunPython.noop),
    ]
