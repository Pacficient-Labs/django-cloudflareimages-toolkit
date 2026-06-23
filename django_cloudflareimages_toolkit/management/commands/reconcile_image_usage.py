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
            # Fetch each model's rows once, then evaluate every tracked field
            # against them (a model may declare several CloudflareImageFields).
            instances = list(model.objects.all().order_by("pk"))
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

        if not dry_run:
            self._backfill_images()

        self._report(dry_run, upserts, deletes)

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
                f"{prefix} track {upserts} reference(s), "
                f"remove {deletes} stale row(s)."
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
