"""
Tests for migration SSOT / determinism (guards the 0006 index-name fix).

The model ``Meta.indexes`` names are the single source of truth for the index
identifiers; the migrations must stay in lock-step with them. A drift between the
two — e.g. an unnamed index whose auto-generated name differs from the one baked
into a historical migration, or a name over Django's 30-char ``models.E034``
limit — makes ``makemigrations`` emit a spurious ``RenameIndex`` into the
installed package. That is exactly the bug ``0006_pin_index_names`` fixes; these
tests keep it from regressing.

Principles enforced:

* **SSOT / Determinism** — :func:`test_no_missing_migrations` runs Django's
  (deterministic) autodetector and fails if the model state and the migration
  graph disagree, so the models stay the single source the migrations mirror.
* **Determinism** — :func:`test_model_index_names_are_explicit_and_valid`
  asserts every index/constraint name is pinned (not auto-generated, so it can't
  vary by Django version) and within the cross-backend length limit.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.apps import apps
from django.core.management import call_command

APP_LABEL = "django_cloudflareimages_toolkit"
# Django models.E034: an index/constraint name cannot exceed 30 characters
# (the most restrictive supported backend). 0001/0003 shipped 31-char names.
MAX_NAME_LEN = 30


@pytest.mark.django_db(databases="__all__")
def test_no_missing_migrations():
    """``makemigrations --check`` detects no changes for this app.

    Enforces SSOT (the models are the source; the migrations mirror them) and
    determinism (the autodetector is reproducible). Fails loudly if a model
    change — including an index/constraint rename — has no matching migration.
    """
    out = StringIO()
    try:
        call_command(
            "makemigrations",
            APP_LABEL,
            "--check",
            "--dry-run",
            stdout=out,
            stderr=out,
        )
    except SystemExit:  # --check exits non-zero when changes would be generated.
        pytest.fail(
            "Model state is out of sync with the migrations "
            "(run `python manage.py makemigrations`):\n" + out.getvalue()
        )


def test_model_index_names_are_explicit_and_valid():
    """Every ``Meta.indexes`` / ``Meta.constraints`` entry is named and <=30 chars.

    Explicit names are deterministic across Django versions (no hash-based
    auto-naming), and the length cap is the one 0001/0003 violated. This guards
    both regressions cheaply, without touching the database.
    """
    for model in apps.get_app_config(APP_LABEL).get_models():
        for index in model._meta.indexes:
            assert index.name, (
                f"{model.__name__}: index on {index.fields} has no explicit name"
            )
            assert len(index.name) <= MAX_NAME_LEN, (
                f"{model.__name__}: index name {index.name!r} is "
                f"{len(index.name)} chars (> {MAX_NAME_LEN}; trips models.E034)"
            )
        for constraint in model._meta.constraints:
            assert constraint.name, f"{model.__name__}: unnamed constraint"
            assert len(constraint.name) <= MAX_NAME_LEN, (
                f"{model.__name__}: constraint name {constraint.name!r} is "
                f"{len(constraint.name)} chars (> {MAX_NAME_LEN})"
            )
