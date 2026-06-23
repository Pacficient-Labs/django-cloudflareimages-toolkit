"""
Management command to rebuild the image usage registry from host models.

Signals keep ``ImageUsage`` in sync for ordinary ``save()``/``delete()`` calls, but
bulk operations (``QuerySet.update()``, ``bulk_create``, ``loaddata``, raw SQL)
bypass them. This command reconciles the registry deterministically and
idempotently: it scans every model field discovered by the registry, upserts the
current references, removes stale auto-tracked rows, links references to their
``CloudflareImage`` where possible, and reports orphans and unregistered
references. Running it repeatedly converges to the same state.
"""

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from ...models import CloudflareImage, ImageUsage
from ...registry import (
    MANUAL_FIELD_NAME,
    _extract_cloudflare_id,
    get_models_with_image_fields,
    record_usage,
)


class Command(BaseCommand):
    """Rebuild the image usage registry and report orphans/unregistered refs."""

    help = "Rebuild the image usage registry from host models and report orphans."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        registry = get_models_with_image_fields(refresh=True)

        upserts = 0
        # Collect the PKs of every row that should be removed across all three
        # phases into one set, so the reported count is deduplicated and a
        # dry-run reports exactly what a real run would delete (a row that is
        # both "stale" in the main loop and "dangling"/"undiscovered" is counted
        # once). Deletion happens once at the end.
        to_delete: set = set()

        # Stable iteration order keeps the operation deterministic.
        for model in sorted(registry, key=lambda m: m._meta.label):
            content_type = ContentType.objects.get_for_model(model)
            # Fetch each model's rows once via the *base* manager, then evaluate
            # every tracked field against them (a model may declare several
            # CloudflareImageFields). The base manager bypasses a filtered default
            # manager (soft-delete / tenant scoping) that would otherwise hide
            # still-referenced rows and get them pruned as stale.
            instances = list(model._base_manager.all().order_by("pk"))
            for field_name in registry[model]:
                current = {}
                for instance in instances:
                    cloudflare_id = _extract_cloudflare_id(
                        getattr(instance, field_name, None)
                    )
                    if cloudflare_id:
                        current[str(instance.pk)] = cloudflare_id

                # Manual rows (``source="manual"``) are owned by the caller and
                # take precedence over auto reconciliation: never count them as
                # stale, never overwrite their ``source`` back to ``"auto"``. A
                # manual row whose ``field_name`` happens to collide with a
                # tracked field's name is therefore safe.
                manual_object_ids = set(
                    ImageUsage.objects.filter(
                        content_type=content_type,
                        field_name=field_name,
                        source=ImageUsage.SOURCE_MANUAL,
                    ).values_list("object_id", flat=True)
                )
                auto_rows = ImageUsage.objects.filter(
                    content_type=content_type, field_name=field_name
                ).exclude(source=ImageUsage.SOURCE_MANUAL)
                existing_ids = set(auto_rows.values_list("object_id", flat=True))
                stale = existing_ids - set(current)
                actionable_current = {
                    oid: cid
                    for oid, cid in current.items()
                    if oid not in manual_object_ids
                }

                upserts += len(actionable_current)
                if stale:
                    to_delete.update(
                        auto_rows.filter(object_id__in=stale).values_list(
                            "pk", flat=True
                        )
                    )

                if not dry_run:
                    with transaction.atomic():
                        for object_id, cloudflare_id in actionable_current.items():
                            record_usage(
                                content_type, object_id, field_name, cloudflare_id
                            )

        to_delete |= self._undiscovered_field_pks(registry)
        to_delete |= self._dangling_pks()

        if not dry_run:
            if to_delete:
                ImageUsage.objects.filter(pk__in=to_delete).delete()
            self._backfill_images()

        self._report(dry_run, upserts, len(to_delete))

    @staticmethod
    def _auto_rows():
        """QuerySet of rows that reconcile is allowed to prune.

        Manual rows (created via ``register_usage``) are protected by their
        ``source`` marker regardless of ``field_name``. Pre-migration rows whose
        ``source`` defaulted to ``"auto"`` but whose label was the legacy
        ``"manual"`` are also protected, so upgrading is non-destructive.
        """
        return ImageUsage.objects.exclude(source=ImageUsage.SOURCE_MANUAL).exclude(
            field_name=MANUAL_FIELD_NAME
        )

    def _undiscovered_field_pks(self, registry) -> set:
        """PKs of auto rows for fields no longer in the registry.

        Covers renamed/removed ``CloudflareImageField``s (their old usage rows
        would otherwise keep their images looking in-use forever). Rows whose
        ``source`` is ``"manual"`` are preserved regardless of ``field_name``.
        """
        discovered = {
            (ContentType.objects.get_for_model(model).pk, field_name)
            for model, fields in registry.items()
            for field_name in fields
        }
        auto = self._auto_rows()
        pks: set = set()
        for content_type_id, field_name in auto.values_list(
            "content_type", "field_name"
        ).distinct():
            if (content_type_id, field_name) in discovered:
                continue
            pks.update(
                auto.filter(
                    content_type_id=content_type_id, field_name=field_name
                ).values_list("pk", flat=True)
            )
        return pks

    def _dangling_pks(self) -> set:
        """PKs of usage rows whose owning object no longer exists.

        Covers manually-registered owners and removed models/objects that bypass
        the post_delete signal, so a deleted owner can't keep an image looking
        in-use. Grouped by content type to avoid per-row object lookups.
        """
        pks: set = set()
        content_type_ids = (
            ImageUsage.objects.values_list("content_type", flat=True)
            .distinct()
            .order_by("content_type")
        )
        for content_type_id in content_type_ids:
            content_type = ContentType.objects.get_for_id(content_type_id)
            rows = ImageUsage.objects.filter(content_type=content_type)
            model = content_type.model_class()
            if model is None:
                # The model (or its app) was removed entirely.
                pks.update(rows.values_list("pk", flat=True))
                continue
            existing = {
                str(pk) for pk in model._base_manager.values_list("pk", flat=True)
            }
            pks.update(row.pk for row in rows if row.object_id not in existing)
        return pks

    def _backfill_images(self):
        """Link any unlinked usages to a now-existing CloudflareImage record."""
        unlinked_ids = (
            ImageUsage.objects.filter(image__isnull=True)
            .values_list("cloudflare_id", flat=True)
            .distinct()
        )
        for cloudflare_id in unlinked_ids:
            image = CloudflareImage.objects.filter(cloudflare_id=cloudflare_id).first()
            if image is not None:
                ImageUsage.objects.filter(
                    cloudflare_id=cloudflare_id, image__isnull=True
                ).update(image=image)

    def _report(self, dry_run, upserts, deletes):
        """Print a summary plus orphan / unregistered counts."""
        prefix = "DRY RUN: would" if dry_run else "Reconciled:"
        # ``upserts`` counts current references re-asserted (idempotent, so most
        # are no-ops); ``deletes`` counts only genuinely stale rows removed.
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix} track {upserts} reference(s), remove {deletes} stale row(s)."
            )
        )

        total = ImageUsage.objects.count()
        orphans = CloudflareImage.objects.filter(usages__isnull=True).count()
        unregistered = ImageUsage.objects.filter(image__isnull=True).count()

        self.stdout.write(f"Total usages: {total}")
        self.stdout.write(
            (self.style.WARNING if orphans else self.style.SUCCESS)(
                f"Orphaned images (no usages): {orphans}"
            )
        )
        self.stdout.write(
            (self.style.WARNING if unregistered else self.style.SUCCESS)(
                f"Unregistered references (no image record): {unregistered}"
            )
        )
