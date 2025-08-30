"""
Django admin configuration for Cloudflare Images Direct Creator Upload.

This module provides comprehensive admin interfaces for monitoring and managing
Cloudflare images, upload logs, and system statistics.
"""

import json

from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .exceptions import CloudflareImagesError
from .models import CloudflareImage, ImageUploadLog, ImageUploadStatus
from .services import cloudflare_service


class ImageUploadLogInline(admin.TabularInline):
    """Inline admin for image upload logs."""

    model = ImageUploadLog
    extra = 0
    readonly_fields = ("timestamp", "event_type", "message", "formatted_data")
    fields = ("timestamp", "event_type", "message", "formatted_data")
    ordering = ("-timestamp",)

    def formatted_data(self, obj):
        """Format JSON data for display."""
        if obj.data:
            try:
                formatted = json.dumps(obj.data, indent=2)
                return format_html('<pre style="font-size: 11px;">{}</pre>', formatted)
            except (TypeError, ValueError):
                return str(obj.data)
        return "-"

    formatted_data.short_description = "Data"


@admin.register(CloudflareImage)
class CloudflareImageAdmin(admin.ModelAdmin):
    """Admin interface for CloudflareImage model."""

    list_display = (
        "cloudflare_id_display",
        "user_display",
        "status_display",
        "filename_display",
        "file_size_display",
        "created_at",
        "expires_at",
        "is_expired_display",
        "thumbnail_preview",
        "actions_display",
    )

    list_filter = (
        "status",
        "require_signed_urls",
        "created_at",
        "uploaded_at",
        "expires_at",
        ("user", admin.RelatedOnlyFieldListFilter),
    )

    search_fields = (
        "cloudflare_id",
        "filename",
        "original_filename",
        "user__username",
        "user__email",
    )

    readonly_fields = (
        "id",
        "cloudflare_id",
        "upload_url_display",
        "status",
        "created_at",
        "updated_at",
        "uploaded_at",
        "expires_at",
        "width",
        "height",
        "format",
        "variants_display",
        "cloudflare_metadata_display",
        "is_expired_display",
        "is_uploaded_display",
        "is_ready_display",
        "public_url_display",
        "thumbnail_url_display",
        "image_preview",
        "transformation_examples",
    )

    fields = (
        "id",
        "cloudflare_id",
        "user",
        "filename",
        "original_filename",
        "content_type",
        "file_size",
        "width",
        "height",
        "format",
        "upload_url_display",
        "status",
        "require_signed_urls",
        "metadata",
        "created_at",
        "updated_at",
        "uploaded_at",
        "expires_at",
        "variants_display",
        "cloudflare_metadata_display",
        "is_expired_display",
        "is_uploaded_display",
        "is_ready_display",
        "public_url_display",
        "thumbnail_url_display",
        "image_preview",
        "transformation_examples",
    )

    inlines = [ImageUploadLogInline]

    actions = [
        "check_status_action",
        "mark_as_expired",
        "delete_from_cloudflare_action",
        "refresh_all_status",
    ]

    list_per_page = 25
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related("user")
            .prefetch_related("logs")
        )

    # Display methods
    def cloudflare_id_display(self, obj):
        """Display Cloudflare ID with copy button."""
        if obj.cloudflare_id:
            return format_html(
                '<span title="Click to copy" style="cursor: pointer; font-family: monospace;" '
                "onclick=\"navigator.clipboard.writeText('{}'); "
                "this.style.backgroundColor='#90EE90'; "
                "setTimeout(() => this.style.backgroundColor='', 1000)\">{}</span>",
                obj.cloudflare_id,
                obj.cloudflare_id[:20] + "..."
                if len(obj.cloudflare_id) > 20
                else obj.cloudflare_id,
            )
        return "-"

    cloudflare_id_display.short_description = "Cloudflare ID"

    def user_display(self, obj):
        """Display user with link to user admin."""
        if obj.user:
            url = reverse("admin:auth_user_change", args=[obj.user.pk])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return "-"

    user_display.short_description = "User"

    def status_display(self, obj):
        """Display status with color coding."""
        colors = {
            ImageUploadStatus.PENDING: "#ffc107",  # Yellow
            ImageUploadStatus.DRAFT: "#17a2b8",  # Blue
            ImageUploadStatus.UPLOADED: "#28a745",  # Green
            ImageUploadStatus.FAILED: "#dc3545",  # Red
            ImageUploadStatus.EXPIRED: "#6c757d",  # Gray
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_display.short_description = "Status"

    def filename_display(self, obj):
        """Display filename with truncation."""
        if obj.filename:
            if len(obj.filename) > 30:
                return format_html(
                    '<span title="{}">{}</span>',
                    obj.filename,
                    obj.filename[:27] + "...",
                )
            return obj.filename
        return obj.original_filename or "-"

    filename_display.short_description = "Filename"

    def file_size_display(self, obj):
        """Display file size in human readable format."""
        if obj.file_size:
            if obj.file_size < 1024:
                return f"{obj.file_size} B"
            elif obj.file_size < 1024 * 1024:
                return f"{obj.file_size / 1024:.1f} KB"
            else:
                return f"{obj.file_size / (1024 * 1024):.1f} MB"
        return "-"

    file_size_display.short_description = "File Size"

    def is_expired_display(self, obj):
        """Display expiry status with icon."""
        if obj.is_expired:
            return format_html('<span style="color: #dc3545;">🔴 Expired</span>')
        else:
            return format_html('<span style="color: #28a745;">🟢 Valid</span>')

    is_expired_display.short_description = "Expiry Status"

    def thumbnail_preview(self, obj):
        """Display thumbnail preview if available."""
        if obj.is_uploaded and obj.thumbnail_url:
            return format_html(
                '<img src="{}" style="max-width: 50px; max-height: 50px; border-radius: 4px;" />',
                obj.thumbnail_url,
            )
        return "-"

    thumbnail_preview.short_description = "Preview"

    def actions_display(self, obj):
        """Display action buttons."""
        actions = []

        if obj.status in [ImageUploadStatus.PENDING, ImageUploadStatus.DRAFT]:
            actions.append(
                format_html(
                    '<a href="javascript:void(0)" onclick="checkStatus(\'{}\')" '
                    'style="color: #007cba; text-decoration: none;">🔄 Check</a>',
                    obj.pk,
                )
            )

        if obj.is_uploaded and obj.public_url:
            actions.append(
                format_html(
                    '<a href="{}" target="_blank" style="color: #007cba; text-decoration: none;">👁️ View</a>',
                    obj.public_url,
                )
            )

        return format_html(" | ".join(actions)) if actions else "-"

    actions_display.short_description = "Actions"

    # Readonly field methods
    def upload_url_display(self, obj):
        """Display upload URL with security."""
        if obj.upload_url and not obj.is_expired:
            return format_html(
                '<div style="font-family: monospace; font-size: 11px; word-break: break-all; '
                'background: #f8f9fa; padding: 8px; border-radius: 4px; max-width: 400px;">'
                "<strong>⚠️ Sensitive:</strong> {}</div>",
                obj.upload_url,
            )
        elif obj.is_expired:
            return format_html('<span style="color: #dc3545;">Expired</span>')
        return "-"

    upload_url_display.short_description = "Upload URL"

    def variants_display(self, obj):
        """Display available variants."""
        if obj.variants:
            variants_html = []
            for variant in obj.variants:
                variants_html.append(
                    format_html(
                        '<a href="{}" target="_blank" style="display: block; margin: 2px 0; '
                        'font-size: 11px; color: #007cba;">{}</a>',
                        variant,
                        variant.split("/")[-1] if "/" in variant else variant,
                    )
                )
            return format_html("<div>{}</div>", "".join(variants_html))
        return "-"

    variants_display.short_description = "Variants"

    def cloudflare_metadata_display(self, obj):
        """Display Cloudflare metadata."""
        if obj.cloudflare_metadata:
            try:
                formatted = json.dumps(obj.cloudflare_metadata, indent=2)
                return format_html('<pre style="font-size: 11px;">{}</pre>', formatted)
            except (TypeError, ValueError):
                return str(obj.cloudflare_metadata)
        return "-"

    cloudflare_metadata_display.short_description = "Cloudflare Metadata"

    def is_uploaded_display(self, obj):
        """Display upload status."""
        return "✅ Yes" if obj.is_uploaded else "❌ No"

    is_uploaded_display.short_description = "Is Uploaded"

    def is_ready_display(self, obj):
        """Display ready status."""
        return "✅ Ready" if obj.is_ready else "❌ Not Ready"

    is_ready_display.short_description = "Is Ready"

    def public_url_display(self, obj):
        """Display public URL with link."""
        if obj.public_url:
            return format_html(
                '<a href="{}" target="_blank" style="font-family: monospace; font-size: 11px;">{}</a>',
                obj.public_url,
                obj.public_url,
            )
        return "-"

    public_url_display.short_description = "Public URL"

    def thumbnail_url_display(self, obj):
        """Display thumbnail URL with link."""
        if obj.thumbnail_url:
            return format_html(
                '<a href="{}" target="_blank" style="font-family: monospace; font-size: 11px;">{}</a>',
                obj.thumbnail_url,
                obj.thumbnail_url,
            )
        return "-"

    thumbnail_url_display.short_description = "Thumbnail URL"

    def image_preview(self, obj):
        """Display larger image preview."""
        if obj.is_uploaded and obj.public_url:
            return format_html(
                '<div style="text-align: center;">'
                '<img src="{}" style="max-width: 300px; max-height: 200px; border: 1px solid #ddd; border-radius: 4px;" />'
                "</div>",
                obj.thumbnail_url or obj.public_url,
            )
        return "-"

    image_preview.short_description = "Image Preview"

    def transformation_examples(self, obj):
        """Display transformation examples."""
        if obj.is_uploaded and obj.public_url:
            from .transformations import CloudflareImageVariants

            examples = [
                (
                    "Thumbnail 100px",
                    CloudflareImageVariants.thumbnail(obj.public_url, 100),
                ),
                ("Avatar 80px", CloudflareImageVariants.avatar(obj.public_url, 80)),
                (
                    "Product 200px",
                    CloudflareImageVariants.product_image(obj.public_url, 200),
                ),
            ]

            html_parts = []
            for name, url in examples:
                html_parts.append(
                    format_html(
                        '<div style="margin: 5px 0;">'
                        "<strong>{}:</strong><br>"
                        '<img src="{}" style="max-width: 80px; max-height: 80px; margin: 2px; border: 1px solid #ddd;" />'
                        "</div>",
                        name,
                        url,
                    )
                )

            return format_html("<div>{}</div>", "".join(html_parts))
        return "-"

    transformation_examples.short_description = "Transformation Examples"

    # Admin actions
    def check_status_action(self, request, queryset):
        """Check status for selected images."""
        updated_count = 0
        error_count = 0

        for image in queryset:
            try:
                cloudflare_service.check_image_status(image)
                updated_count += 1
            except CloudflareImagesError:
                error_count += 1

        if updated_count:
            self.message_user(
                request, f"Successfully updated status for {updated_count} images."
            )
        if error_count:
            self.message_user(
                request, f"Failed to update {error_count} images.", level="WARNING"
            )

    check_status_action.short_description = "Check status from Cloudflare"

    def mark_as_expired(self, request, queryset):
        """Mark selected images as expired."""
        count = queryset.update(status=ImageUploadStatus.EXPIRED)
        self.message_user(request, f"Marked {count} images as expired.")

    mark_as_expired.short_description = "Mark as expired"

    def delete_from_cloudflare_action(self, request, queryset):
        """Delete selected images from Cloudflare."""
        deleted_count = 0
        error_count = 0

        for image in queryset:
            try:
                cloudflare_service.delete_image(image)
                image.delete()
                deleted_count += 1
            except CloudflareImagesError:
                error_count += 1

        if deleted_count:
            self.message_user(
                request, f"Successfully deleted {deleted_count} images from Cloudflare."
            )
        if error_count:
            self.message_user(
                request, f"Failed to delete {error_count} images.", level="WARNING"
            )

    delete_from_cloudflare_action.short_description = "Delete from Cloudflare"

    def refresh_all_status(self, request, queryset):
        """Refresh status for all non-final status images."""
        pending_images = queryset.filter(
            status__in=[ImageUploadStatus.PENDING, ImageUploadStatus.DRAFT]
        )

        updated_count = 0
        for image in pending_images:
            try:
                cloudflare_service.check_image_status(image)
                updated_count += 1
            except CloudflareImagesError:
                pass

        self.message_user(request, f"Refreshed status for {updated_count} images.")

    refresh_all_status.short_description = "Refresh all pending/draft status"

    class Media:
        js = ("admin/js/cloudflare_images_admin.js",)
        css = {"all": ("admin/css/cloudflare_images_admin.css",)}


@admin.register(ImageUploadLog)
class ImageUploadLogAdmin(admin.ModelAdmin):
    """Admin interface for ImageUploadLog model."""

    list_display = (
        "timestamp",
        "image_display",
        "event_type",
        "message_display",
        "user_display",
    )

    list_filter = (
        "event_type",
        "timestamp",
        ("image__user", admin.RelatedOnlyFieldListFilter),
    )

    search_fields = (
        "image__cloudflare_id",
        "event_type",
        "message",
        "image__user__username",
    )

    readonly_fields = ("image", "event_type", "message", "formatted_data", "timestamp")

    fields = ("image", "event_type", "message", "formatted_data", "timestamp")

    list_per_page = 50
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    def get_queryset(self, request):
        """Optimize queryset."""
        return super().get_queryset(request).select_related("image", "image__user")

    def image_display(self, obj):
        """Display image with link."""
        if obj.image:
            url = reverse(
                "admin:django_cloudflareimages_toolkit_cloudflareimage_change",
                args=[obj.image.pk],
            )
            return format_html(
                '<a href="{}">{}</a>',
                url,
                obj.image.cloudflare_id[:20] + "..."
                if len(obj.image.cloudflare_id) > 20
                else obj.image.cloudflare_id,
            )
        return "-"

    image_display.short_description = "Image"

    def message_display(self, obj):
        """Display message with truncation."""
        if len(obj.message) > 50:
            return format_html(
                '<span title="{}">{}</span>', obj.message, obj.message[:47] + "..."
            )
        return obj.message

    message_display.short_description = "Message"

    def user_display(self, obj):
        """Display user."""
        if obj.image and obj.image.user:
            return obj.image.user.username
        return "-"

    user_display.short_description = "User"

    def formatted_data(self, obj):
        """Format JSON data for display."""
        if obj.data:
            try:
                formatted = json.dumps(obj.data, indent=2)
                return format_html(
                    '<pre style="font-size: 11px; max-height: 200px; overflow-y: auto;">{}</pre>',
                    formatted,
                )
            except (TypeError, ValueError):
                return str(obj.data)
        return "-"

    formatted_data.short_description = "Data"


# Custom admin site configuration
class CloudflareImagesAdminSite(admin.AdminSite):
    """Custom admin site for Cloudflare Images."""

    site_header = "Cloudflare Images Administration"
    site_title = "Cloudflare Images Admin"
    index_title = "Cloudflare Images Management"

    def index(self, request, extra_context=None):
        """Custom index with statistics."""
        extra_context = extra_context or {}

        # Get statistics
        total_images = CloudflareImage.objects.count()
        uploaded_images = CloudflareImage.objects.filter(
            status=ImageUploadStatus.UPLOADED
        ).count()
        pending_images = CloudflareImage.objects.filter(
            status=ImageUploadStatus.PENDING
        ).count()
        expired_images = CloudflareImage.objects.filter(
            expires_at__lt=timezone.now()
        ).count()

        # Recent activity
        recent_uploads = CloudflareImage.objects.filter(
            uploaded_at__isnull=False
        ).order_by("-uploaded_at")[:5]

        recent_logs = ImageUploadLog.objects.select_related("image").order_by(
            "-timestamp"
        )[:10]

        extra_context.update(
            {
                "cloudflare_stats": {
                    "total_images": total_images,
                    "uploaded_images": uploaded_images,
                    "pending_images": pending_images,
                    "expired_images": expired_images,
                    "upload_success_rate": (uploaded_images / total_images * 100)
                    if total_images > 0
                    else 0,
                },
                "recent_uploads": recent_uploads,
                "recent_logs": recent_logs,
            }
        )

        return super().index(request, extra_context)


# Register with custom admin site if desired
# cloudflare_admin_site = CloudflareImagesAdminSite(name='cloudflare_admin')
# cloudflare_admin_site.register(CloudflareImage, CloudflareImageAdmin)
# cloudflare_admin_site.register(ImageUploadLog, ImageUploadLogAdmin)
