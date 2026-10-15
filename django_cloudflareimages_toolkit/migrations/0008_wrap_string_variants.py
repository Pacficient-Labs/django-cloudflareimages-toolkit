"""Wrap bare-string ``CloudflareImage.variants`` values in a list.

Rows written outside the normal register path could hold a single delivery URL
as a JSON string instead of a list; readers then found no URL at all (#41).
``CloudflareImage.save()`` now normalises the shape, and this cleans up rows
that already have it. Done in Python so it runs on every supported backend.
"""

from django.db import migrations


def wrap_string_variants(apps, schema_editor):
    CloudflareImage = apps.get_model(
        "django_cloudflareimages_toolkit", "CloudflareImage"
    )
    db = schema_editor.connection.alias
    rows = CloudflareImage.objects.using(db).values_list("pk", "variants")
    for pk, variants in rows.iterator():
        if isinstance(variants, str):
            CloudflareImage.objects.using(db).filter(pk=pk).update(
                variants=[variants] if variants else []
            )


class Migration(migrations.Migration):
    dependencies = [
        ("django_cloudflareimages_toolkit", "0007_cloudflareimage_user"),
    ]

    operations = [
        migrations.RunPython(wrap_string_variants, migrations.RunPython.noop),
    ]
