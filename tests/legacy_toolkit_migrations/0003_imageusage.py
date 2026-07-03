import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Create the ImageUsage reverse-index model.

    No data migration: usage rows are populated by signals on subsequent saves,
    and existing references can be backfilled in one pass by running
    ``python manage.py reconcile_image_usage`` after deploying.
    """

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("django_cloudflareimages_toolkit", "0002_cloudflareimage_creator"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImageUsage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("object_id", models.CharField(db_index=True, max_length=255)),
                ("field_name", models.CharField(max_length=255)),
                ("cloudflare_id", models.CharField(db_index=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "image",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="usages",
                        to="django_cloudflareimages_toolkit.cloudflareimage",
                    ),
                ),
            ],
            options={
                "db_table": "cloudflare_image_usages",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="imageusage",
            index=models.Index(
                fields=["content_type", "object_id"],
                name="cloudflare__content_9a5e2d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="imageusage",
            index=models.Index(
                fields=["cloudflare_id"], name="cloudflare__cloudfl_e0652c_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="imageusage",
            constraint=models.UniqueConstraint(
                fields=("content_type", "object_id", "field_name"),
                name="uniq_image_usage_per_field",
            ),
        ),
    ]
