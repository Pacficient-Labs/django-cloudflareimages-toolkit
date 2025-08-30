"""
Management command to clean up expired image upload URLs.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from django_cloudflareimages_toolkit import CloudflareImage, ImageUploadStatus


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

    def handle(self, *args, **options):
        """Handle the command execution."""
        now = timezone.now()
        dry_run = options["dry_run"]
        delete_expired = options["delete"]
        days_threshold = options["days"]

        # Find expired images
        expired_images = CloudflareImage.objects.filter(
            expires_at__lt=now,
            status__in=[ImageUploadStatus.PENDING, ImageUploadStatus.DRAFT],
        )

        expired_count = expired_images.count()

        if expired_count == 0:
            self.stdout.write(self.style.SUCCESS("No expired images found."))
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
