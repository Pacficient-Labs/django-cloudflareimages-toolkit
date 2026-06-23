"""Backfill ``CloudflareImage.last_referenced_at`` for existing references.

Without this, upgrades from 0003 leave every image's ``last_referenced_at`` as
``NULL``. The runtime code then falls back to ``created_at`` for orphan
retention, so a long-lived image whose final reference is removed shortly after
the upgrade can be deleted immediately by ``cleanup_expired_images
--delete-orphans``. This pass marks images that have at least one existing
``ImageUsage`` row as "referenced now" so the retention clock starts from the
upgrade moment for those rows.
"""

from django.db import migrations


def backfill_last_referenced(apps, schema_editor):
    CloudflareImage = apps.get_model(
        "django_cloudflareimages_toolkit", "CloudflareImage"
    )
    ImageUsage = apps.get_model("django_cloudflareimages_toolkit", "ImageUsage")

    from django.utils import timezone

    now = timezone.now()
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
    ).update(last_referenced_at=now)


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
