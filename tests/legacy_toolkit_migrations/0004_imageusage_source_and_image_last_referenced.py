from django.db import migrations, models


class Migration(migrations.Migration):
    """Add usage-source marker and last-referenced timestamp.

    No data migration is needed: the new ``source`` field defaults to ``"auto"``
    for existing rows, and the cleanup command treats null ``last_referenced_at``
    as "never touched by the registry" and falls back to the legacy
    ``created_at`` clock for those rows.
    """

    dependencies = [
        ("django_cloudflareimages_toolkit", "0003_imageusage"),
    ]

    operations = [
        migrations.AddField(
            model_name="cloudflareimage",
            name="last_referenced_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="imageusage",
            name="source",
            field=models.CharField(
                choices=[("auto", "Auto"), ("manual", "Manual")],
                db_index=True,
                default="auto",
                max_length=10,
            ),
        ),
    ]
