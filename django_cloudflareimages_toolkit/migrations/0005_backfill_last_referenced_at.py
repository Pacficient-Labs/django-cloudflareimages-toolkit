"""Backfill registry bookkeeping for upgrades from 0003.

Two things must be repaired for rows that predate the new columns:

1. ``CloudflareImage.last_referenced_at`` — without it, upgrades leave every
   value ``NULL`` and the orphan-retention fallback (``created_at``) could
   delete a long-lived image the moment its last reference is removed. We mark
   every image that currently has at least one ``ImageUsage`` row as
   "referenced now."

2. ``ImageUsage.source`` — the new column defaults to ``"auto"`` for existing
   rows, but rows created through the manual API with a custom label (e.g.
   ``register_usage(obj, ..., field_name="hero")``) would then be treated as
   auto-managed and pruned by ``reconcile_image_usage``. We reclassify any row
   whose ``(content_type, field_name)`` is *not* a currently-discovered
   ``CloudflareImageField`` as ``source="manual"`` — auto rows only ever use a
   real tracked field name, so anything else must have come from the manual
   API.
"""

from django.db import migrations


def backfill_registry_bookkeeping(apps, schema_editor):
    CloudflareImage = apps.get_model(
        "django_cloudflareimages_toolkit", "CloudflareImage"
    )
    ImageUsage = apps.get_model("django_cloudflareimages_toolkit", "ImageUsage")
    ContentType = apps.get_model("contenttypes", "ContentType")

    from django.utils import timezone

    from django_cloudflareimages_toolkit.models import ImageUsage as RuntimeImageUsage
    from django_cloudflareimages_toolkit.registry import (
        get_models_with_image_fields,
    )

    db = schema_editor.connection.alias

    # 1) last_referenced_at backfill for images with existing references.
    referenced_ids = list(
        ImageUsage.objects.using(db)
        .filter(image__isnull=False)
        .values_list("image_id", flat=True)
        .distinct()
    )
    if referenced_ids:
        CloudflareImage.objects.using(db).filter(
            pk__in=referenced_ids,
            last_referenced_at__isnull=True,
        ).update(last_referenced_at=timezone.now())

    # 2) Reclassify legacy manual rows. Build the set of currently-discovered
    #    (content_type_id, field_name) pairs from the installed models.
    discovered = set()
    for model, fields in get_models_with_image_fields(refresh=True).items():
        ct = (
            ContentType.objects.using(db)
            .filter(app_label=model._meta.app_label, model=model._meta.model_name)
            .first()
        )
        if ct is None:
            continue
        for field_name in fields:
            discovered.add((ct.id, field_name))

    rows = (
        ImageUsage.objects.using(db)
        .all()
        .only("pk", "content_type_id", "field_name", "source")
    )
    manual_pks = [
        row.pk
        for row in rows
        if (row.content_type_id, row.field_name) not in discovered
    ]
    if manual_pks:
        ImageUsage.objects.using(db).filter(pk__in=manual_pks).update(
            source=RuntimeImageUsage.SOURCE_MANUAL
        )


class Migration(migrations.Migration):
    dependencies = [
        (
            "django_cloudflareimages_toolkit",
            "0004_imageusage_source_and_image_last_referenced",
        ),
    ]

    operations = [
        migrations.RunPython(backfill_registry_bookkeeping, migrations.RunPython.noop),
    ]
