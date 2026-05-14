---
title: "CloudflareImageField"
description: "Reference for CloudflareImageField and CloudflareImageFieldValue."
---

Source file: `django_cloudflareimages_toolkit/fields.py`

Import paths:

```python
from django_cloudflareimages_toolkit.fields import (
    CloudflareImageField,
    CloudflareImageFieldValue,
)
```

## `CloudflareImageField`

```python
class CloudflareImageField(models.Field):
    def __init__(
        self,
        variants: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        require_signed_urls: bool = False,
        max_file_size: int | None = None,
        allowed_formats: list[str] | None = None,
        **kwargs,
    ) -> None: ...
```

### Constructor options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `variants` | `list[str] \| None` | `None` | Declared variant names for widget configuration. |
| `metadata` | `dict[str, Any] \| None` | `None` | Default metadata passed into the widget config. |
| `require_signed_urls` | `bool` | `False` | Stored on the field instance and passed into the widget. |
| `max_file_size` | `int \| None` | `None` | Client-side validation hint for the widget. |
| `allowed_formats` | `list[str] \| None` | `None` | Defaults to `["jpeg", "png", "gif", "webp"]`. |
| `**kwargs` | model field kwargs | — | `max_length`, `blank`, and `null` default to field-friendly values if omitted. |

### Public methods

```python
def get_internal_type(self) -> str: ...
def to_python(self, value: Any) -> CloudflareImageFieldValue | None: ...
def from_db_value(self, value: Any, expression, connection) -> CloudflareImageFieldValue | None: ...
def get_prep_value(self, value: Any) -> str | None: ...
def formfield(self, **kwargs) -> forms.Field: ...
def validate(self, value: Any, model_instance) -> None: ...
def deconstruct(self) -> tuple: ...
```

Example:

```python
class Profile(models.Model):
    avatar = CloudflareImageField(
        metadata={"kind": "avatar"},
        allowed_formats=["jpeg", "png", "webp"],
        blank=True,
        null=True,
    )
```

## `CloudflareImageFieldValue`

This is the runtime wrapper returned by `to_python()`.

```python
class CloudflareImageFieldValue:
    def __init__(self, cloudflare_id: str, field: CloudflareImageField | None = None) -> None: ...
```

### Public methods and properties

```python
@property
def cloudflare_image(self) -> CloudflareImage | None: ...

def get_url(self, variant: str = "public") -> str | None: ...
def get_signed_url(self, variant: str = "public", expiry: int = 3600) -> str | None: ...
def delete(self) -> bool: ...
def get_metadata(self) -> dict[str, Any]: ...
def update_metadata(self, metadata: dict[str, Any]) -> bool: ...

@property
def variants(self) -> list[str]: ...

@property
def file_size(self) -> int | None: ...

@property
def filename(self) -> str | None: ...

@property
def uploaded_at(self): ...

@property
def is_ready(self) -> bool: ...
```

Behavior notes:

- `get_url()` first tries the related `CloudflareImage` row, then falls back to constructing `https://imagedelivery.net/{account_hash}/{cloudflare_id}/{variant}` from settings.
- `delete()` delegates to `cloudflare_service.delete_image()` only if the related `CloudflareImage` row exists.
- `update_metadata()` only mutates the local model row; it does not call `CloudflareImagesService.update_image()`.

Example:

```python
profile = Profile.objects.get(pk=1)

if profile.avatar:
    print(profile.avatar.cloudflare_id)
    print(profile.avatar.get_url("thumbnail"))
    profile.avatar.update_metadata({"approved": True})
```
