from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_cloudflareimages_toolkit", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="cloudflareimage",
            name="creator",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
    ]
