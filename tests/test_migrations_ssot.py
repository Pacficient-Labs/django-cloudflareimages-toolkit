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
    both regressions cheaply, without touching the database. Violations are
    collected so the failure message reports every offender at once.
    """
    problems: list[str] = []
    for model in apps.get_app_config(APP_LABEL).get_models():
        named = [(idx.name, idx.fields, "index") for idx in model._meta.indexes]
        named += [
            (c.name, getattr(c, "fields", None), "constraint")
            for c in model._meta.constraints
        ]
        for name, fields, kind in named:
            if not name:
                problems.append(f"{model.__name__}: unnamed {kind} on {fields}")
            elif len(name) > MAX_NAME_LEN:
                problems.append(
                    f"{model.__name__}: {kind} name {name!r} is {len(name)} "
                    f"chars (> {MAX_NAME_LEN}; trips models.E034)"
                )
    if problems:
        pytest.fail(
            "Implicit or over-long index/constraint names:\n" + "\n".join(problems)
        )
