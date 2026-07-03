"""Add ``CloudflareImage.user`` and its index, owned by a migration that can
safely depend on ``AUTH_USER_MODEL``.

Why this exists: ``0001_initial`` used to create this FK (and the
``user``+``status`` index) directly, which put a swappable dependency on
``AUTH_USER_MODEL`` onto the app's *initial* migration. That makes the
toolkit unusable for any project whose custom user model (or a model sharing
an initial migration with the user model) also has a FK to
``CloudflareImage``: ``consumer.0001 -> toolkit.0001`` (needs the user model)
while ``toolkit.0001 -> consumer.0001`` (consumer defines the user model) is
an unresolvable ``CircularDependencyError``. ``0001_initial`` no longer
creates ``user`` for exactly this reason; this migration -- which is not
anyone's initial migration -- carries the swappable dependency instead.

Why the operations below are custom (``AddFieldIfMissing``/
``AddIndexIfMissing``) rather than plain ``AddField``/``AddIndex``: databases
that already ran the *original* ``0001_initial`` already have this column,
its FK constraint, and (as of ``0006``) this index physically in place. This
migration is new to those databases, so a plain ``AddField``/``AddIndex``
would run for real there and fail with a "column/index already exists"
error. There is no way to give this migration different operations for
"fresh install" vs. "upgrading install" -- both run the literal same file --
so instead each operation checks the table via the schema editor's own
introspection and skips the database-level change when it's already present,
while still updating Django's migration *state* unconditionally (via the
inherited, unmodified ``state_forwards``) so the ORM model matches on both
kinds of installs.

The user/status index needs one extra case. There are three possible
physical states of that index when this migration runs:

* **fresh install** -- the trimmed ``0001`` never created it, so no index on
  ``(user, status)`` exists; ``AddIndexIfMissing`` creates it under the
  pinned name ``cfimg_user_status_idx``.
* **upgrade that applied legacy ``0006``** -- legacy ``0001`` created the
  index as ``cloudflare_i_user_id_b8c8a5_idx`` and legacy ``0006`` already
  renamed it to ``cfimg_user_status_idx``; the pinned name is present, so we
  skip.
* **upgrade that applied legacy ``0001``-``0005`` but NOT legacy ``0006``**
  -- the index still exists under its original auto-generated name
  ``cloudflare_i_user_id_b8c8a5_idx``. Our edited ``0006`` no longer renames
  it (that rename was removed along with the field), so if we only checked
  for the pinned name we would create a *second* index on the same columns.
  Instead, ``AddIndexIfMissing`` is given the legacy name via
  ``legacy_names`` and RENAMEs the existing index to the pinned name,
  converging every install to exactly one index under one name.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class AddFieldIfMissing(migrations.AddField):
    """``AddField``, but skips the ALTER TABLE if the column already exists."""

    def _column_name(self, state, app_label):
        model = state.apps.get_model(app_label, self.model_name)
        return model._meta.get_field(self.name).column

    def _existing_columns(self, schema_editor, table_name):
        with schema_editor.connection.cursor() as cursor:
            return {
                col.name
                for col in schema_editor.connection.introspection.get_table_description(
                    cursor, table_name
                )
            }

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        column = self._column_name(to_state, app_label)
        if column in self._existing_columns(schema_editor, model._meta.db_table):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        column = self._column_name(from_state, app_label)
        if column not in self._existing_columns(schema_editor, model._meta.db_table):
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)


class AddIndexIfMissing(migrations.AddIndex):
    """``AddIndex`` that converges to the pinned name without duplicating.

    If the pinned index name already exists, do nothing. Otherwise, if any
    name in ``legacy_names`` exists on the table (the index created under an
    older auto-generated name by a previous release), RENAME it to the pinned
    name rather than creating a second index on the same columns. Only when
    no equivalent index exists at all is a new one created.
    """

    def __init__(self, *args, legacy_names=(), **kwargs):
        self.legacy_names = tuple(legacy_names)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, args, kwargs = super().deconstruct()
        if self.legacy_names:
            kwargs["legacy_names"] = self.legacy_names
        return name, args, kwargs

    def _existing_index_names(self, schema_editor, table_name):
        with schema_editor.connection.cursor() as cursor:
            return set(
                schema_editor.connection.introspection.get_constraints(
                    cursor, table_name
                )
            )

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        existing = self._existing_index_names(schema_editor, model._meta.db_table)
        if self.index.name in existing:
            return
        for legacy in self.legacy_names:
            if legacy in existing:
                # Same columns, older name: converge in place instead of
                # creating a duplicate. rename_index renames on backends that
                # support it and drops+recreates on those that don't (e.g.
                # SQLite); both need only the index name and fields.
                old_index = models.Index(fields=self.index.fields, name=legacy)
                schema_editor.rename_index(model, old_index, self.index)
                return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        if self.index.name not in self._existing_index_names(
            schema_editor, model._meta.db_table
        ):
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):
    dependencies = [
        ("django_cloudflareimages_toolkit", "0006_pin_index_names"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        AddFieldIfMissing(
            model_name="cloudflareimage",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cloudflare_images",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        AddIndexIfMissing(
            model_name="cloudflareimage",
            index=models.Index(fields=["user", "status"], name="cfimg_user_status_idx"),
            # The original auto-generated name from legacy 0001, in case this
            # install never applied legacy 0006's rename before upgrading.
            legacy_names=["cloudflare_i_user_id_b8c8a5_idx"],
        ),
    ]
