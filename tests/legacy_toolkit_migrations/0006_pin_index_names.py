"""Pin deterministic, valid index names.

Migrations ``0001`` and ``0003`` shipped ``Meta.indexes`` whose names were
auto-generated at 31 characters — one over Django's 30-char ``models.E034``
limit — and never matched the names a newer Django computes for the model.
That mismatch made ``makemigrations`` want to emit a spurious ``RenameIndex``
into the installed package (site-packages) on every run.

This migration renames those indexes to short, explicit, valid names that are
now pinned in each model's ``Meta.indexes`` (see ``models.py``), so the model
state and the migration state agree and ``makemigrations`` is a no-op. Existing
databases are renamed in place; fresh databases create the original names in
``0001``/``0003`` and are renamed here, so every database converges to the same
names regardless of install age.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("django_cloudflareimages_toolkit", "0005_backfill_last_referenced_at"),
    ]

    operations = [
        # CloudflareImage (created in 0001)
        migrations.RenameIndex(
            model_name="cloudflareimage",
            new_name="cfimg_user_status_idx",
            old_name="cloudflare_i_user_id_b8c8a5_idx",
        ),
        migrations.RenameIndex(
            model_name="cloudflareimage",
            new_name="cfimg_status_created_idx",
            old_name="cloudflare_i_status_0b7e8c_idx",
        ),
        migrations.RenameIndex(
            model_name="cloudflareimage",
            new_name="cfimg_expires_idx",
            old_name="cloudflare_i_expires_a8f9d2_idx",
        ),
        # ImageUploadLog (created in 0001)
        migrations.RenameIndex(
            model_name="imageuploadlog",
            new_name="cfimg_log_image_ts_idx",
            old_name="cloudflare_i_image_i_c4e5f6_idx",
        ),
        migrations.RenameIndex(
            model_name="imageuploadlog",
            new_name="cfimg_log_event_ts_idx",
            old_name="cloudflare_i_event_t_d7g8h9_idx",
        ),
        # ImageUsage (created in 0003)
        migrations.RenameIndex(
            model_name="imageusage",
            new_name="cfimg_usage_ct_obj_idx",
            old_name="cloudflare__content_9a5e2d_idx",
        ),
        migrations.RenameIndex(
            model_name="imageusage",
            new_name="cfimg_usage_cfid_idx",
            old_name="cloudflare__cloudfl_e0652c_idx",
        ),
    ]
