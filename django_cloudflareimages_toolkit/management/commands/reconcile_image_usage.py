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
        deletes = 0

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

                existing_ids = set(
                    ImageUsage.objects.filter(
                        content_type=content_type, field_name=field_name
                    ).values_list("object_id", flat=True)
                )
                stale = existing_ids - set(current)

                upserts += len(current)
                deletes += len(stale)

                if not dry_run:
                    with transaction.atomic():
                        for object_id, cloudflare_id in current.items():
                            record_usage(
                                content_type, object_id, field_name, cloudflare_id
                            )
                        if stale:
                            ImageUsage.objects.filter(
                                content_type=content_type,
                                field_name=field_name,
                                object_id__in=stale,
                            ).delete()

        # Both prune passes participate in the delete count for dry-run so the
        # reported total matches what a real run would remove.
        deletes += self._prune_undiscovered_fields(registry, dry_run=dry_run)
        deletes += self._prune_dangling(dry_run=dry_run)
        if not dry_run:
            self._backfill_images()

        self._report(dry_run, upserts, deletes)

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

    def _prune_undiscovered_fields(self, registry, dry_run: bool = False) -> int:
        """Drop auto-tracked rows for fields no longer in the registry.

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
        seen_pairs = auto.values_list("content_type", "field_name").distinct()
        removed = 0
        for content_type_id, field_name in seen_pairs:
            if (content_type_id, field_name) in discovered:
                continue
            qs = auto.filter(content_type_id=content_type_id, field_name=field_name)
            if dry_run:
                removed += qs.count()
            else:
                count, _ = qs.delete()
                removed += count
        return removed

    def _prune_dangling(self, dry_run: bool = False) -> int:
        """Delete usage rows whose owning object no longer exists.

        Covers manually-registered owners and removed models/objects that bypass
        the post_delete signal, so a deleted owner can't keep an image looking
        in-use. Grouped by content type to avoid per-row object lookups.
        """
        removed = 0
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
                removed += rows.count()
                if not dry_run:
                    rows.delete()
                continue
            existing = {
                str(pk) for pk in model._base_manager.values_list("pk", flat=True)
            }
            stale_pks = [row.pk for row in rows if row.object_id not in existing]
            if stale_pks:
                removed += len(stale_pks)
                if not dry_run:
                    ImageUsage.objects.filter(pk__in=stale_pks).delete()
        return removed

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
