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
)
```

Important public classes from `admin.py`:

```python
class ImageUploadLogInline(admin.TabularInline): ...
class CloudflareImageAdmin(admin.ModelAdmin): ...
class ImageUploadLogAdmin(admin.ModelAdmin): ...
class CloudflareImagesAdminSite(admin.AdminSite): ...
```

`CloudflareImageAdmin` provides:

- status, expiry, file-size, and thumbnail displays
- log inline rendering
- actions for checking status, marking expired, deleting from Cloudflare, and refreshing status
- read-only diagnostic fields such as rendered variants and Cloudflare metadata

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

Example:

```bash
python manage.py cleanup_expired_images --dry-run
python manage.py cleanup_expired_images --delete --days 30
```

Together, the widget, admin, and command form the operational shell around the core upload and transformation APIs.
