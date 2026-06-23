"""
Management command to clean up expired image upload URLs.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from django_cloudflareimages_toolkit import CloudflareImage, ImageUploadStatus
from django_cloudflareimages_toolkit.exceptions import CloudflareImagesError
from django_cloudflareimages_toolkit.services import cloudflare_service


class Command(BaseCommand):
    """Command to clean up expired image upload URLs."""

    help = "Clean up expired image upload URLs and mark them as expired"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be cleaned up without making changes",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete expired images instead of just marking them as expired",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Delete images that have been expired for this many days (default: 7)",
        )
        parser.add_argument(
            "--delete-orphans",
            action="store_true",
            help=(
                "Delete uploaded images referenced by no content (orphans) from "
                "Cloudflare and the database. Relies on the usage registry being "
                "current — run 'reconcile_image_usage' first for accuracy."
            ),
        )
        parser.add_argument(
            "--orphan-days",
            type=int,
            default=30,
            help="Only delete orphans older than this many days (default: 30)",
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        now = timezone.now()
        dry_run = options["dry_run"]
        delete_expired = options["delete"]
        days_threshold = options["days"]
        delete_orphans = options["delete_orphans"]
        orphan_days = options["orphan_days"]

        # Find expired images
        expired_images = CloudflareImage.objects.filter(
            expires_at__lt=now,
            status__in=[ImageUploadStatus.PENDING, ImageUploadStatus.DRAFT],
        )

        expired_count = expired_images.count()

        if expired_count == 0:
            self.stdout.write(self.style.SUCCESS("No expired images found."))
            if delete_orphans:
                self._cleanup_orphans(now, orphan_days, dry_run)
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: Would mark {expired_count} expired images"
                )
            )
            for image in expired_images[:10]:  # Show first 10
                self.stdout.write(
                    f"  - {image.cloudflare_id} (expired: {image.expires_at})"
                )
            if expired_count > 10:
                self.stdout.write(f"  ... and {expired_count - 10} more")
            if delete_orphans:
                self._cleanup_orphans(now, orphan_days, dry_run)
            return

        # Mark images as expired
        with transaction.atomic():
            updated = expired_images.update(status=ImageUploadStatus.EXPIRED)
            self.stdout.write(self.style.SUCCESS(f"Marked {updated} images as expired"))

        # Delete old expired images if requested
        if delete_expired:
            delete_threshold = now - timezone.timedelta(days=days_threshold)
            old_expired_images = CloudflareImage.objects.filter(
                status=ImageUploadStatus.EXPIRED, updated_at__lt=delete_threshold
            )

            old_count = old_expired_images.count()
            if old_count > 0:
                with transaction.atomic():
                    old_expired_images.delete()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Deleted {old_count} old expired images "
                            f"(older than {days_threshold} days)"
                        )
                    )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"No old expired images found "
                        f"(older than {days_threshold} days)"
                    )
                )

        # Optionally delete orphaned (unreferenced) uploaded images.
        if delete_orphans:
            self._cleanup_orphans(now, orphan_days, dry_run)

    def _cleanup_orphans(self, now, orphan_days, dry_run):
        """Delete uploaded images referenced by no content (orphans).

        The retention clock is "time since this image was last referenced," not
        "time since upload." For images that have ever been recorded as
        referenced (``last_referenced_at`` is set), eligibility means
        ``last_referenced_at`` is older than the threshold. For images that have
        never been touched by the registry (``last_referenced_at IS NULL``) we
        fall back to ``created_at`` so legacy data and never-referenced uploads
        both keep working.

        Accuracy depends on the usage registry being current; run
        ``reconcile_image_usage`` first if host data changed via bulk operations.
        """
        from django.db.models import Q

        threshold = now - timezone.timedelta(days=orphan_days)
        orphans = CloudflareImage.objects.filter(
            Q(last_referenced_at__lt=threshold)
            | Q(last_referenced_at__isnull=True, created_at__lt=threshold),
            usages__isnull=True,
            status=ImageUploadStatus.UPLOADED,
        )

        orphan_count = orphans.count()
        if orphan_count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No orphaned images found (older than {orphan_days} days)"
                )
            )
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: Would delete {orphan_count} orphaned image(s) "
                    f"(older than {orphan_days} days)"
                )
            )
            for image in orphans[:10]:
                self.stdout.write(f"  - {image.cloudflare_id}")
            if orphan_count > 10:
                self.stdout.write(f"  ... and {orphan_count - 10} more")
            return

        deleted = 0
        errors = 0
        for image in orphans:
            try:
                # missing_ok=True: an image already absent in Cloudflare (404)
                # counts as deleted, so the local row is still removed and a
                # re-run after a partial failure converges instead of looping
                # on the same error forever.
                cloudflare_service.delete_image(image, missing_ok=True)
                image.delete()
                deleted += 1
            except CloudflareImagesError:
                errors += 1

        self.stdout.write(
            self.style.SUCCESS(f"Deleted {deleted} orphaned image(s) from Cloudflare")
        )
        if errors:
            self.stdout.write(
                self.style.WARNING(f"Failed to delete {errors} orphaned image(s)")
            )
