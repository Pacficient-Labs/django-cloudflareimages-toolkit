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

Why the rename is by columns, not by a hard-coded ``old_name``
--------------------------------------------------------------
The original ``0001``/``0003`` shipped their ``Meta.indexes`` **without** an
explicit ``name=``, so Django auto-generated the physical index name at
apply-time — and that algorithm's output changed across Django versions (the
prefix flipped ``cloudflare_i_`` -> ``cloudflare__`` and the hash changed). A
plain ``RenameIndex(old_name="cloudflare_i_status_0b7e8c_idx")`` therefore only
matches on databases first created under the one Django version that produced
that exact string; on a database whose indexes were created under a different
version the ``old_name`` does not exist and the whole ``migrate`` aborts with
``UndefinedTable``/``ProgrammingError``.

The migration *state*, by contrast, is version-independent: ``0001``/``0003``
now pin the pre-rename names explicitly, so in state the index is always called
``cloudflare_i_status_0b7e8c_idx`` on every install. So ``state_forwards``
(inherited unchanged from ``RenameIndex``) keeps using ``old_name``; only the
*physical* rename introspects the real index sitting on the target columns and
renames whatever is actually there — the same defensiveness ``0007`` uses for
its ``(user, status)`` index. This survives the very version drift the plain
rename could not.

NOTE: The rename for the ``user``+``status`` index
(``cloudflare_i_user_id_b8c8a5_idx`` -> ``cfimg_user_status_idx``) that used to
live here has been removed. ``0001_initial`` no longer creates the ``user``
field or that index at all (see the note there and in
``0007_cloudflareimage_user``), so on a fresh install there is nothing named
``cloudflare_i_user_id_b8c8a5_idx`` to rename by the time this migration runs;
``0007`` creates that index directly under its final name instead. This is
safe for already-installed databases: this migration already ran there with
the rename included, and editing already-applied migration content has no
effect on them.
"""

from django.db import migrations, models


def _rename_index_by_columns(schema_editor, model, fields, target_name):
    """Rename the ``Meta.indexes`` index on ``fields`` to ``target_name``.

    Finds the index by the columns it covers rather than by a guessed physical
    name, so it is independent of the Django version that first created it.
    No-op when the index is already named ``target_name`` (fresh installs, or
    databases that already converged) or when no matching index exists.

    Disambiguation: a field with both ``db_index=True`` and a ``Meta`` index on
    the same single column (e.g. ``ImageUsage.cloudflare_id``) has *two*
    single-column indexes. Django auto-names the ``Meta`` index with an ``_idx``
    suffix while the implicit ``db_index`` one has no such suffix, so we only
    consider ``_idx`` names — matching exactly the index whose name this
    migration pins.
    """
    columns = [model._meta.get_field(name.lstrip("-")).column for name in fields]
    with schema_editor.connection.cursor() as cursor:
        constraints = schema_editor.connection.introspection.get_constraints(
            cursor, model._meta.db_table
        )
    if target_name in constraints:
        return
    matches = [
        name
        for name, info in constraints.items()
        if info.get("index")
        and not info.get("unique")
        and not info.get("primary_key")
        and not info.get("foreign_key")
        and list(info.get("columns") or []) == columns
        and name.endswith("_idx")
    ]
    if len(matches) != 1:
        return
    schema_editor.rename_index(
        model,
        models.Index(fields=fields, name=matches[0]),
        models.Index(fields=fields, name=target_name),
    )


class RenameIndexIfExists(migrations.RenameIndex):
    """``RenameIndex`` that renames the *physical* index by its columns.

    ``state_forwards``/``state_backwards`` and ``deconstruct`` are inherited
    unchanged (they operate on ``old_name``, which is version-independent in
    migration state). Only the database half is overridden to locate the real
    index by the columns it covers, so it converges regardless of which Django
    version generated the original physical name.
    """

    def _index_fields(self, state, app_label, name):
        model = state.apps.get_model(app_label, self.model_name)
        for index in model._meta.indexes:
            if index.name == name:
                return index.fields
        return None

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        fields = self._index_fields(from_state, app_label, self.old_name)
        if fields:
            _rename_index_by_columns(schema_editor, model, fields, self.new_name)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        fields = self._index_fields(to_state, app_label, self.old_name)
        if fields:
            _rename_index_by_columns(schema_editor, model, fields, self.old_name)


class Migration(migrations.Migration):
    dependencies = [
        ("django_cloudflareimages_toolkit", "0005_backfill_last_referenced_at"),
    ]

    operations = [
        # CloudflareImage (created in 0001)
        RenameIndexIfExists(
            model_name="cloudflareimage",
            new_name="cfimg_status_created_idx",
            old_name="cloudflare_i_status_0b7e8c_idx",
        ),
        RenameIndexIfExists(
            model_name="cloudflareimage",
            new_name="cfimg_expires_idx",
            old_name="cloudflare_i_expires_a8f9d2_idx",
        ),
        # ImageUploadLog (created in 0001)
        RenameIndexIfExists(
            model_name="imageuploadlog",
            new_name="cfimg_log_image_ts_idx",
            old_name="cloudflare_i_image_i_c4e5f6_idx",
        ),
        RenameIndexIfExists(
            model_name="imageuploadlog",
            new_name="cfimg_log_event_ts_idx",
            old_name="cloudflare_i_event_t_d7g8h9_idx",
        ),
        # ImageUsage (created in 0003)
        RenameIndexIfExists(
            model_name="imageusage",
            new_name="cfimg_usage_ct_obj_idx",
            old_name="cloudflare__content_9a5e2d_idx",
        ),
        RenameIndexIfExists(
            model_name="imageusage",
            new_name="cfimg_usage_cfid_idx",
            old_name="cloudflare__cloudfl_e0652c_idx",
        ),
    ]
