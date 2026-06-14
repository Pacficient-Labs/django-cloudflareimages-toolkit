from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_cloudflareimages_toolkit", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="cloudflareimage",
            name="creator",
            # Explicit empty-string default backfills existing rows on every
            # backend; preserve_default=False keeps the model field default-free.
            field=models.CharField(
                blank=True, db_index=True, default="", max_length=255
            ),
            preserve_default=False,
        ),
    ]
