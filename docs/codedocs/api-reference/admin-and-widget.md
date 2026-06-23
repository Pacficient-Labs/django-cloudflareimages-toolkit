---
title: "Admin and Widget"
description: "Reference for the Django admin classes, the custom widget, and the cleanup command entry point."
---

Source files: `django_cloudflareimages_toolkit/admin.py`, `django_cloudflareimages_toolkit/widgets.py`, `django_cloudflareimages_toolkit/management/commands/cleanup_expired_images.py`

## `CloudflareImageWidget`

Import path:

```python
from django_cloudflareimages_toolkit.widgets import CloudflareImageWidget
```

### Constructor

```python
class CloudflareImageWidget(forms.TextInput):
    def __init__(
        self,
        variants: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        require_signed_urls: bool = False,
        max_file_size: int | None = None,
        allowed_formats: list[str] | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> None: ...
```

### Public methods

```python
def format_value(self, value): ...
def render(
    self,
    name: str,
    value: Any,
    attrs: dict[str, Any] | None = None,
    renderer=None,
) -> SafeText: ...
```

Behavior summary:

- Uses `template_name = "django_cloudflareimages_toolkit/widgets/cloudflare_image_widget.html"`.
- If template rendering fails, falls back to inline HTML and JavaScript from `_render_fallback()`.
- Injects widget config as JSON for variants, metadata, signed URL preference, size limit, and allowed formats.

## Admin classes

Import path:

```python
from django_cloudflareimages_toolkit.admin import (
    CloudflareImageAdmin,
    ImageUploadLogInline,
    ImageUsageInline,
)
```

Important public classes from `admin.py`:

```python
class ImageUsageInline(admin.TabularInline): ...
class ImageUploadLogInline(admin.TabularInline): ...
class CloudflareImageAdmin(admin.ModelAdmin): ...
class ImageUploadLogAdmin(admin.ModelAdmin): ...
class ImageUsageAdmin(admin.ModelAdmin): ...
class CloudflareImagesAdminSite(admin.AdminSite): ...
```

`CloudflareImageAdmin` provides:

- status, expiry, file-size, and thumbnail displays
- a **thumbnail gallery view** of the changelist (toggle to the table with the "Table view" link), driven by `change_list.html` and the `cfimg_status_color` template filter
- a **"Used by"** inline (`ImageUsageInline`) linking to the content that references the image, plus a `usage_count` column and an **Orphaned** filter
- log inline rendering
- actions for checking status, marking expired, deleting from Cloudflare, and refreshing status
- read-only diagnostic fields such as rendered variants and Cloudflare metadata

`ImageUsageAdmin` lists usage records with links to the referencing objects and an
**Unregistered** filter (references with no `CloudflareImage`). The
`CloudflareImagesAdminSite` stats dashboard also reports tracked fields, total
usages, orphaned images, and unregistered references. See the
[Image Usage Registry](../image-usage-registry) page.

Because `admin.py` uses `@admin.register`, the model admin is activated automatically when the app is installed.

## Management command

Import path:

```bash
python manage.py cleanup_expired_images
```

Public command methods:

```python
class Command(BaseCommand):
    def add_arguments(self, parser) -> None: ...
    def handle(self, *args, **options) -> None: ...
```

Arguments:

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dry-run` | boolean | `False` | Print the first matching expired rows without changing data. |
| `--delete` | boolean | `False` | Delete old expired rows after marking current stale rows. |
| `--days` | integer | `7` | Threshold for deleting already-expired rows. |
| `--delete-orphans` | boolean | `False` | Delete uploaded images referenced by no content (from Cloudflare + DB). |
| `--orphan-days` | integer | `30` | Only delete orphans older than this many days. |

Example:

```bash
python manage.py cleanup_expired_images --dry-run
python manage.py cleanup_expired_images --delete --days 30
python manage.py cleanup_expired_images --delete-orphans --orphan-days 30
```

### `reconcile_image_usage`

Rebuilds the [image usage registry](../image-usage-registry) from host models —
the fix for bulk operations that bypass signals — and reports orphans and
unregistered references. Idempotent and safe to schedule.

```bash
python manage.py reconcile_image_usage            # rebuild + report
python manage.py reconcile_image_usage --dry-run  # report only, no writes
```

Together, the widget, admin, and commands form the operational shell around the core upload and transformation APIs.
