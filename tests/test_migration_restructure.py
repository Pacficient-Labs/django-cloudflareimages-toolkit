"""Verify the 0001/0006/0007 restructuring that removed the swappable
(AUTH_USER_MODEL) dependency from ``0001_initial``.

Two real risk scenarios are exercised end-to-end, against real sqlite
databases and the real migration executor (not hand-rolled DDL assertions):

* :func:`test_upgrade_from_pre_restructure_install` simulates a database that
  already applied the *original* (pre-fix) 0001-0006 -- i.e. one that already
  has ``cloudflare_images.user_id`` and its index -- and then upgrades onto
  the new migration graph. This is the scenario the whole
  ``AddFieldIfMissing``/``AddIndexIfMissing`` mechanism in
  ``0007_cloudflareimage_user`` exists to protect: a plain ``AddField``/
  ``AddIndex`` would fail there with a "column/index already exists" error.

* :func:`test_consumer_pinned_to_0001_has_no_circular_dependency` and
  :func:`test_consumer_pinned_to_leaf_still_cycles` cover the actual bug
  report -- a consuming app whose own ``0001_initial`` FKs ``CloudflareImage``
  *and* defines ``AUTH_USER_MODEL`` -- using the toolkit's real on-disk
  dependencies. Django pins such a consumer's dependency to the toolkit
  *leaf*, which still cycles (the residual limitation); the supported fix is
  for the consumer to pin to ``0001_initial``, which the restructuring made
  safe. Both facts are asserted so behavior and docs can't drift apart.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404: only runs an isolated test child, see _run_consumer_child
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from django.conf import settings
from django.db import connections
from django.db.migrations.recorder import MigrationRecorder

APP_LABEL = "django_cloudflareimages_toolkit"


def _fresh_sqlite_alias(alias, tmp_path, db_name):
    """Register a brand-new sqlite file database under ``alias``.

    ``ConnectionHandler.settings`` is a ``cached_property`` that, once
    accessed (which happens during pytest-django's session-scoped test DB
    setup, well before this runs), holds the *same* dict object as
    ``settings.DATABASES`` -- so mutating that dict in place is visible to
    the connection handler too. ``ConnectionHandler.databases`` itself is a
    read-only property in modern Django, so it cannot be reassigned; and
    ``configure_settings()`` (which fills in defaults like ``TIME_ZONE``,
    ``OPTIONS``, ``TEST``) only ever runs once, at that first access -- so an
    alias inserted afterwards must already carry those defaults itself.
    """
    path = tmp_path / db_name
    settings.DATABASES[alias] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(path),
        "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "OPTIONS": {},
        "TIME_ZONE": None,
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
        "TEST": {
            "CHARSET": None,
            "COLLATION": None,
            "MIGRATE": True,
            "MIRROR": None,
            "NAME": None,
        },
    }
    return alias


def _indexes_on(connection, table, columns):
    """Return the names of every index on ``table`` covering exactly ``columns``.

    Used to prove convergence: after upgrade there must be exactly one index
    on ``(user_id, status)``, under the pinned name -- no legacy duplicate.
    """
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table)
    return [
        name
        for name, c in constraints.items()
        if c.get("index") and c.get("columns") == columns
    ]


def _teardown_alias(alias):
    # This runs in a test's ``finally``; it must never raise, or it would
    # mask the real failure. ``ConnectionHandler.__delitem__`` can raise
    # either ``AttributeError`` or ``KeyError`` depending on whether the
    # per-thread connection was ever opened, so both are swallowed.
    try:
        connections[alias].close()
    except Exception:
        pass
    try:
        del connections[alias]
    except (AttributeError, KeyError):
        pass  # connection was registered but never actually opened
    settings.DATABASES.pop(alias, None)


def test_upgrade_from_pre_restructure_install(tmp_path, settings, django_db_blocker):
    """An install that already ran the old 0001-0006 upgrades cleanly onto 0007.

    Uses a standalone sqlite file database (not the shared pytest-django test
    db) via ``django_db_blocker.unblock()``, since this alias is created ad
    hoc and pytest-django's normal ``django_db`` marker only permits aliases
    known at fixture-setup time.
    """
    from django.core.management import call_command

    alias = _fresh_sqlite_alias("legacy_upgrade", tmp_path, "legacy.sqlite3")
    with django_db_blocker.unblock():
        try:
            # Phase 1: build the database as it existed *before* this
            # restructuring, using the real (unedited) historical migration
            # files -- not a hand-authored approximation of that schema.
            call_command("migrate", "contenttypes", database=alias, verbosity=0)
            call_command("migrate", "auth", database=alias, verbosity=0)
            settings.MIGRATION_MODULES = {
                APP_LABEL: "tests.legacy_toolkit_migrations",
            }
            call_command("migrate", APP_LABEL, database=alias, verbosity=0)

            recorder = MigrationRecorder(connections[alias])
            applied_before = {
                name for app, name in recorder.applied_migrations() if app == APP_LABEL
            }
            assert applied_before == {
                "0001_initial",
                "0002_cloudflareimage_creator",
                "0003_imageusage",
                "0004_imageusage_source_and_image_last_referenced",
                "0005_backfill_last_referenced_at",
                "0006_pin_index_names",
            }

            with connections[alias].cursor() as cursor:
                columns_before = {
                    col.name
                    for col in connections[alias].introspection.get_table_description(
                        cursor, "cloudflare_images"
                    )
                }
            assert "user_id" in columns_before

            # Phase 2: "upgrade the package" -- point back at the real (new)
            # migrations, which is 0001..0007 with the trimmed 0001/0006 and
            # the new idempotent 0007. Because 0001-0006 are already recorded
            # as applied (by name), Django won't rerun them; only 0007 is new.
            # (Reassign rather than `del`: pytest-django's `settings` fixture
            # tracks this as a deleted override, not a reset-to-default, if we
            # `del` it -- and Django's own default MIGRATION_MODULES is `{}`
            # anyway.)
            settings.MIGRATION_MODULES = {}

            call_command("migrate", APP_LABEL, database=alias, verbosity=0)

            applied_after = {
                name for app, name in recorder.applied_migrations() if app == APP_LABEL
            }
            assert "0007_cloudflareimage_user" in applied_after

            with connections[alias].cursor() as cursor:
                # A list (not a set) so the occurrence count below is meaningful.
                columns_after = [
                    col.name
                    for col in connections[alias].introspection.get_table_description(
                        cursor, "cloudflare_images"
                    )
                ]
                constraints_after = connections[alias].introspection.get_constraints(
                    cursor, "cloudflare_images"
                )

            # No duplicate column: still exactly one `user_id`.
            assert columns_after.count("user_id") == 1
            assert "cfimg_user_status_idx" in constraints_after
            # Exactly one index on (user_id, status), under the pinned name.
            idx = _indexes_on(
                connections[alias], "cloudflare_images", ["user_id", "status"]
            )
            assert idx == ["cfimg_user_status_idx"], idx

            # Re-running migrate is a no-op: nothing pending, nothing errors.
            call_command("migrate", APP_LABEL, database=alias, verbosity=0)
        finally:
            settings.MIGRATION_MODULES = {}
            _teardown_alias(alias)


def test_upgrade_from_pre_restructure_install_without_legacy_0006(
    tmp_path, settings, django_db_blocker
):
    """Upgrade from an install that applied legacy 0001-0005 but NOT 0006.

    This is the edge Copilot flagged: such a database still has the user index
    under its original auto-generated name ``cloudflare_i_user_id_b8c8a5_idx``
    (legacy 0006's rename never ran, and the edited 0006 no longer performs
    it). If 0007 only checked for the pinned name it would create a *second*
    index on the same columns. The ``legacy_names`` handling must instead
    converge to a single index under the pinned name.
    """
    from django.core.management import call_command

    alias = _fresh_sqlite_alias("legacy_no6", tmp_path, "legacy_no6.sqlite3")
    with django_db_blocker.unblock():
        try:
            call_command("migrate", "contenttypes", database=alias, verbosity=0)
            call_command("migrate", "auth", database=alias, verbosity=0)
            settings.MIGRATION_MODULES = {
                APP_LABEL: "tests.legacy_toolkit_migrations",
            }
            # Stop at 0005 -- deliberately do NOT apply legacy 0006.
            call_command(
                "migrate",
                APP_LABEL,
                "0005_backfill_last_referenced_at",
                database=alias,
                verbosity=0,
            )

            recorder = MigrationRecorder(connections[alias])
            applied = {n for a, n in recorder.applied_migrations() if a == APP_LABEL}
            assert "0005_backfill_last_referenced_at" in applied
            assert "0006_pin_index_names" not in applied

            # Precondition: the index exists under its *legacy* name only.
            legacy_idx = _indexes_on(
                connections[alias], "cloudflare_images", ["user_id", "status"]
            )
            assert legacy_idx == ["cloudflare_i_user_id_b8c8a5_idx"], legacy_idx

            # Upgrade the package: run the real 0006 (edited) + 0007.
            settings.MIGRATION_MODULES = {}
            call_command("migrate", APP_LABEL, database=alias, verbosity=0)

            applied = {n for a, n in recorder.applied_migrations() if a == APP_LABEL}
            assert {"0006_pin_index_names", "0007_cloudflareimage_user"} <= applied

            # Convergence: exactly one index on the columns, pinned name, no
            # leftover legacy-named duplicate.
            idx = _indexes_on(
                connections[alias], "cloudflare_images", ["user_id", "status"]
            )
            assert idx == ["cfimg_user_status_idx"], idx

            with connections[alias].cursor() as cursor:
                cols = [
                    c.name
                    for c in connections[alias].introspection.get_table_description(
                        cursor, "cloudflare_images"
                    )
                ]
            assert cols.count("user_id") == 1

            # Idempotent re-run.
            call_command("migrate", APP_LABEL, database=alias, verbosity=0)
        finally:
            settings.MIGRATION_MODULES = {}
            _teardown_alias(alias)


def test_toolkit_initial_migration_has_no_dependencies():
    """``0001_initial`` must declare zero dependencies (no swappable dep).

    This is the load-bearing fact the rest of the restructuring rests on: a
    consuming app is only safe to FK ``CloudflareImage`` from its own
    ``0001_initial`` if the toolkit's ``0001_initial`` needs nothing back from
    that app (or from whatever app defines ``AUTH_USER_MODEL``).
    """
    from django.db.migrations.loader import MigrationLoader

    loader = MigrationLoader(None, ignore_no_migrations=True)
    migration = loader.disk_migrations[(APP_LABEL, "0001_initial")]
    assert migration.dependencies == []


def _build_consumer_graph(consumer_dep_on, *, resolve_swappable_to_consumer):
    """Build a real toolkit migration graph plus a synthetic consumer node.

    ``consumer_dep_on`` is the toolkit migration name the consumer's
    ``0001_initial`` depends on (its FK to ``CloudflareImage``). Every toolkit
    migration is added with its *real* on-disk dependencies; intra-app edges
    and (optionally) the swappable ``AUTH_USER_MODEL`` edge are wired, so the
    graph reflects what Django actually builds rather than a hand-picked shape.

    When ``resolve_swappable_to_consumer`` is True the swappable dependency
    resolves to ``consumer_app.0001_initial`` -- i.e. the consumer app is the
    one that defines ``AUTH_USER_MODEL`` (the pathological case). External
    (contenttypes/auth) dependencies are skipped; they don't participate in the
    consumer<->toolkit cycle.
    """
    from django.db.migrations.graph import MigrationGraph
    from django.db.migrations.loader import MigrationLoader

    loader = MigrationLoader(None, ignore_no_migrations=True)
    toolkit_keys = sorted(k for k in loader.disk_migrations if k[0] == APP_LABEL)

    graph = MigrationGraph()
    consumer = ("consumer_app", "0001_initial")
    graph.add_node(consumer, None)
    for key in toolkit_keys:
        graph.add_node(key, None)

    # consumer.0001 -> toolkit.<consumer_dep_on> (the consumer's FK edge).
    graph.add_dependency(None, consumer, (APP_LABEL, consumer_dep_on))

    for key in toolkit_keys:
        for dep in loader.disk_migrations[key].dependencies:
            # A swappable AUTH_USER_MODEL dependency is a ``SwappableTuple``
            # carrying ``.setting`` (e.g. "auth.User"); by load time it has
            # already resolved to the *current* user model's app (``auth`` in
            # the test env), so detect it by that attribute rather than by the
            # "__setting__" sentinel, which is gone.
            if getattr(dep, "setting", None) is not None:
                if not resolve_swappable_to_consumer:
                    continue
                dep = consumer  # AUTH_USER_MODEL lives in the consumer app.
            elif dep[0] != APP_LABEL:
                continue  # skip external (contenttypes/auth) edges.
            if dep not in graph.node_map:
                graph.add_node(dep, None)
            graph.add_dependency(None, key, dep)
    return graph, toolkit_keys


def test_consumer_pinned_to_0001_has_no_circular_dependency():
    """The supported resolution: consumer depends on toolkit ``0001_initial``.

    This is the edge the restructuring exists to make safe. Because
    ``0001_initial`` is now dependency-free, a consumer app that defines
    ``AUTH_USER_MODEL`` and FKs ``CloudflareImage`` from the same initial
    migration can depend on ``toolkit.0001`` with no cycle -- verified with the
    toolkit's real on-disk dependencies. (Before this change ``0001`` carried
    the swappable dependency itself, so even this edge cycled and no consumer
    edit could fix it.)
    """
    graph, _ = _build_consumer_graph("0001_initial", resolve_swappable_to_consumer=True)
    graph.ensure_not_cyclic()  # must not raise


def test_consumer_pinned_to_leaf_still_cycles():
    """Honest documentation of the residual Django limitation.

    Django's autodetector pins a consumer's FK-to-CloudflareImage dependency to
    the toolkit's *leaf* migration, not to ``0001`` where the model is created
    (``MigrationAutodetector._build_migration_list`` -> ``graph.leaf_nodes()``).
    The leaf transitively depends on the migration that adds the ``user`` FK,
    which depends on ``AUTH_USER_MODEL`` (the consumer), so the auto-generated
    graph still cycles. The toolkit cannot change that resolution; consumers
    must pin to ``0001`` (see README / 0007 docstring). This test asserts the
    limitation is real so the docs can't silently drift from behavior.

    Uses whatever migration is currently the leaf (not a hard-coded name) so
    adding a future ``0008_...`` doesn't spuriously break it -- the cycle holds
    for any leaf, since every leaf descends from the swappable-dependent
    migration.
    """
    from django.db.migrations.graph import CircularDependencyError

    _, toolkit_keys = _build_consumer_graph(
        "0001_initial", resolve_swappable_to_consumer=True
    )
    leaf_name = toolkit_keys[-1][1]

    graph, _ = _build_consumer_graph(leaf_name, resolve_swappable_to_consumer=True)
    with pytest.raises(CircularDependencyError):
        graph.ensure_not_cyclic()


# ---------------------------------------------------------------------------
# End-to-end consumer scenario (real on-disk app, real migration executor)
#
# The graph tests above operate on a synthetic in-process node. The two tests
# below go further: they scaffold a *real* consumer app on disk whose
# ``0001_initial`` BOTH defines the swappable ``AUTH_USER_MODEL`` AND holds a
# ``ForeignKey`` to ``CloudflareImage`` (the exact shape that triggers the bug),
# then drive the real ``makemigrations``/``migrate`` executor.
#
# This must run in a child process: the scenario needs its own
# ``AUTH_USER_MODEL`` (pointing at the consumer app), which is baked into
# settings and the app registry at setup time and cannot be swapped inside the
# already-configured pytest process.
#
# Why the pin is to 0001 and not the leaf (the mechanism, kept here rather than
# in the README so the fix stays a one-liner for readers): Django's autodetector
# does NOT resolve a cross-app FK to "the migration that created the referenced
# model". For an already-installed external app it pins the dependency to that
# app's graph *leaf* -- ``MigrationAutodetector._build_migration_list`` falls to
# ``graph.leaf_nodes(dep.app_label)[0]`` with the comment "we don't know which
# migration contains the target field". The pin is therefore leaf-based, not
# content-based: it is unaffected by which migration last touched
# ``CloudflareImage``, and moving fields between toolkit migrations cannot change
# it. Because the leaf transitively depends on the ``user`` FK (which depends on
# ``AUTH_USER_MODEL`` == the consumer), the auto-generated
# ``consumer.0001 -> toolkit.<leaf> -> consumer.0001`` cycles. The consumer's
# one-time fix -- repointing that dependency at ``0001_initial``, which merely
# creates the table -- is regenerate-stable (Django never rewrites an existing
# migration's ``dependencies``), so it is edited once, not on every regen.
# ---------------------------------------------------------------------------

_CONSUMER_APP = "consumer_userapp"

_CONSUMER_MODELS = """
from django.contrib.auth.models import AbstractBaseUser
from django.db import models


class User(AbstractBaseUser):
    # A valid swappable AUTH_USER_MODEL for this app's 0001_initial. Subclassing
    # AbstractBaseUser satisfies django.contrib.auth's check_user_model
    # (USERNAME_FIELD, REQUIRED_FIELDS, is_anonymous/is_authenticated, unique
    # username), so the child commands never depend on system checks being
    # skipped. AbstractBaseUser adds only password and last_login and no
    # relations, so the migration dependency topology, and the cycle, are
    # unchanged.
    username = models.CharField(max_length=150, unique=True)
    USERNAME_FIELD = "username"


class UserProfile(models.Model):
    # A sibling model created in the SAME 0001_initial as the user model,
    # carrying the ForeignKey to CloudflareImage that triggers the trap. Uses a
    # string reference so importing this module does not import the toolkit
    # (which resolves get_user_model() at import time).
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ForeignKey(
        "django_cloudflareimages_toolkit.CloudflareImage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
"""

_CONSUMER_APPS_PY = """
from django.apps import AppConfig


class ConsumerUserappConfig(AppConfig):
    name = "consumer_userapp"
    default_auto_field = "django.db.models.BigAutoField"
"""

# Child driver. argv[1] is the mode ("trap" or "fix"). It builds an isolated
# Django whose AUTH_USER_MODEL is the consumer's own user model, then reproduces
# the scenario end to end and signals success via exit code + a marker line.
_CONSUMER_CHILD = '''
import os
import sys

MODE = sys.argv[1]
APP = "consumer_userapp"
TK = "django_cloudflareimages_toolkit"

import django
from django.conf import settings

settings.configure(
    DEBUG=True,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ["CHILD_DB"]}},
    INSTALLED_APPS=[
        "django.contrib.contenttypes",
        "django.contrib.auth",
        TK,
        APP,
    ],
    AUTH_USER_MODEL=APP + ".User",
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
)
django.setup()

from django.core.management import call_command
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.exceptions import CircularDependencyError


def toolkit_leaf():
    """The toolkit migration nothing else in the toolkit depends on.

    Uses load=False so the graph (and its cyclic check) is never built -- in the
    trap case building it is exactly what raises, and we need the leaf name
    first. Computed from the on-disk graph so a future 0008_* keeps this honest.
    """
    loader = MigrationLoader(None, load=False)
    loader.load_disk()
    keys = [k for k in loader.disk_migrations if k[0] == TK]
    depended = {
        d[:2]
        for k in keys
        for d in loader.disk_migrations[k].dependencies
        if isinstance(d, tuple) and d[0] == TK
    }
    leaves = [k for k in keys if k not in depended]
    assert len(leaves) == 1, "expected a single toolkit leaf, got %r" % (leaves,)
    return leaves[0], loader


if MODE == "trap":
    call_command("makemigrations", APP, verbosity=0)
    leaf, loader = toolkit_leaf()
    gen = loader.disk_migrations[(APP, "0001_initial")]
    gendeps = {d[:2] for d in gen.dependencies if isinstance(d, tuple)}
    # The autodetector pinned to the LEAF, not to 0001 where the table is made.
    assert leaf in gendeps, "expected pin to leaf %r, got %r" % (leaf, gendeps)
    assert (TK, "0001_initial") not in gendeps, "unexpected 0001 pin: %r" % (gendeps,)
    # Building the real graph with that generated dependency must cycle.
    try:
        MigrationLoader(None)
    except CircularDependencyError as exc:
        print("TRAP_OK pinned_to=%s cycle=%s" % (leaf[1], exc))
        sys.exit(0)
    print("TRAP_FAIL: no CircularDependencyError was raised", file=sys.stderr)
    sys.exit(2)

elif MODE == "fix":
    # Resolve the leaf BEFORE the consumer migration exists, so its module is
    # never imported/cached with the stale (leaf-pinned) dependency.
    leaf, _ = toolkit_leaf()
    call_command("makemigrations", APP, verbosity=0)
    # The one-time edit a consumer makes: repoint the generated leaf dependency
    # at 0001_initial (the migration that CREATES the CloudflareImage table).
    path = os.path.join(os.environ["CHILD_APP_DIR"], "migrations", "0001_initial.py")
    with open(path) as fh:
        text = fh.read()
    # Repoint only the toolkit dependency, matching the migration name as a
    # quoted token (chr(34)=double quote, chr(39)=single) so a stray occurrence
    # of the name in a comment or metadata can never be touched. Replace the
    # first match only and assert one was found.
    _repointed = False
    for _q in (chr(34), chr(39)):
        _tok = _q + leaf[1] + _q
        if _tok in text:
            text = text.replace(_tok, _q + "0001_initial" + _q, 1)
            _repointed = True
            break
    assert _repointed, "leaf %s not found as a quoted dependency token" % (leaf[1],)
    with open(path, "w") as fh:
        fh.write(text)
    # Drop any cached consumer migration module so the executor re-imports the
    # rewritten file from disk rather than a stale copy.
    import importlib

    for _name in [m for m in sys.modules if m.startswith(APP + ".migrations")]:
        del sys.modules[_name]
    importlib.invalidate_caches()
    # Full end-to-end migrate -- not merely an acyclicity check.
    call_command("migrate", verbosity=0)
    # And makemigrations --check must report nothing outstanding (exits nonzero
    # via SystemExit if it would generate anything).
    try:
        call_command("makemigrations", "--check", "--dry-run", verbosity=0)
    except SystemExit as exc:
        if exc.code:
            print("FIX_FAIL: makemigrations --check reported changes", file=sys.stderr)
            sys.exit(3)
    print("FIX_OK: full migrate succeeded and makemigrations --check is clean")
    sys.exit(0)

print("unknown mode %r" % (MODE,), file=sys.stderr)
sys.exit(9)
'''


def _scaffold_consumer_app(base_dir: Path) -> Path:
    """Write a real consumer app package under ``base_dir`` and return its dir."""
    app_dir = base_dir / _CONSUMER_APP
    (app_dir / "migrations").mkdir(parents=True)
    (app_dir / "__init__.py").write_text("")
    (app_dir / "apps.py").write_text(dedent(_CONSUMER_APPS_PY))
    (app_dir / "models.py").write_text(dedent(_CONSUMER_MODELS))
    (app_dir / "migrations" / "__init__.py").write_text("")
    return app_dir


def _run_consumer_child(mode: str, base_dir: Path, app_dir: Path, tmp_path: Path):
    child = tmp_path / f"child_{mode}.py"
    child.write_text(_CONSUMER_CHILD)
    repo_root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
    # The child configures settings itself; it must import the toolkit (repo
    # root) and the freshly-scaffolded consumer app (base_dir).
    env["PYTHONPATH"] = os.pathsep.join([str(repo_root), str(base_dir)])
    env["CHILD_DB"] = str(tmp_path / f"{mode}.sqlite3")
    env["CHILD_APP_DIR"] = str(app_dir)
    # nosec B603: fixed interpreter (sys.executable) with a static argv list, no
    # shell and no untrusted input. stdin is closed and a timeout is set so a
    # stuck child fails fast instead of hanging the suite.
    return subprocess.run(  # nosec B603
        [sys.executable, str(child), mode],
        capture_output=True,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )


def test_consumer_same_migration_pinned_to_leaf_cycles_end_to_end(tmp_path):
    """The trap: a consumer whose 0001 defines the user model AND FKs
    CloudflareImage gets its dependency auto-pinned to the toolkit leaf, and the
    resulting graph is circular.

    This is the real on-disk counterpart to
    :func:`test_consumer_pinned_to_leaf_still_cycles` -- it asserts the
    autodetector's *actual generated* dependency is the leaf (not 0001) and that
    loading that graph raises ``CircularDependencyError``. It documents the trap
    so a future refactor can't silently reintroduce it.
    """
    base = tmp_path / "pkgroot_trap"
    base.mkdir()
    app_dir = _scaffold_consumer_app(base)
    proc = _run_consumer_child("trap", base, app_dir, tmp_path)
    assert proc.returncode == 0, f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    assert "TRAP_OK" in proc.stdout, proc.stdout


def test_consumer_same_migration_pinned_to_0001_migrates_cleanly(tmp_path):
    """The fix: repointing that one generated dependency at ``0001_initial``
    yields a clean, cycle-free FULL migrate plus a no-op ``makemigrations
    --check`` -- against the toolkit's real migrations and a real user model
    defined in the same migration as the CloudflareImage FK.
    """
    base = tmp_path / "pkgroot_fix"
    base.mkdir()
    app_dir = _scaffold_consumer_app(base)
    proc = _run_consumer_child("fix", base, app_dir, tmp_path)
    assert proc.returncode == 0, f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    assert "FIX_OK" in proc.stdout, proc.stdout
