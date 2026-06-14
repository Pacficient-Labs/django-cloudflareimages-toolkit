---
title: "CloudflareImage Models"
description: "Reference for CloudflareImage, ImageUploadLog, and ImageUploadStatus."
---

Source file: `django_cloudflareimages_toolkit/models.py`

Import paths:

```python
from django_cloudflareimages_toolkit.models import (
    CloudflareImage,
    ImageUploadLog,
    ImageUploadStatus,
)
```

## `ImageUploadStatus`

```python
class ImageUploadStatus(models.TextChoices):
    PENDING = "pending"
    DRAFT = "draft"
    UPLOADED = "uploaded"
    FAILED = "failed"
    EXPIRED = "expired"
```

## `CloudflareImageManager`

`CloudflareImage.objects` is a `CloudflareImageManager` that adds one helper on
top of the default manager API:

```python
def register_uploaded(self, cloudflare_id: str, user=None) -> CloudflareImage: ...
```

This is the safe way to persist a client-supplied `cloudflare_id`. It delegates
to `cloudflare_service.register_uploaded_image()`, which verifies the image
against Cloudflare (it must exist and have its draft state cleared) before
creating the local row, populating status, variants, metadata, and creator from
the Cloudflare response. It raises `ImageNotFoundError` (missing) or
`ImageNotReadyError` (still a draft) instead of trusting the input.

> ⚠️ Do **not** call `CloudflareImage.objects.get_or_create(cloudflare_id=<client value>)`
> directly: the ID may not exist, may still be a draft, or belong to another
> user, and you would persist a bare, untrustworthy row. Use `register_uploaded`.

```python
from django_cloudflareimages_toolkit import (
    CloudflareImage,
    ImageNotFoundError,
    ImageNotReadyError,
)

try:
    image = CloudflareImage.objects.register_uploaded(cloudflare_id, user=request.user)
except ImageNotFoundError:
    ...  # not in Cloudflare
except ImageNotReadyError:
    ...  # exists but upload incomplete (still a draft)
```

## `CloudflareImage`

This model tracks one Cloudflare upload slot or uploaded image.

### Important fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `UUIDField` | generated | Local primary key. |
| `cloudflare_id` | `CharField` | — | Unique Cloudflare image ID. |
| `user` | `ForeignKey` | `None` | Optional owner. |
| `upload_url` | `URLField` | — | One-time upload URL issued by Cloudflare. |
| `status` | `CharField` | `pending` | Uses `ImageUploadStatus.choices`. |
| `require_signed_urls` | `BooleanField` | `True` | Local signed-URL requirement flag. |
| `metadata` | `JSONField` | `{}` | Resolved app metadata sent at upload creation time (queryable via `metadata__...`). |
| `creator` | `CharField(255)` | `""` | Cloudflare `creator` value; indexed and queryable. |
| `expires_at` | `DateTimeField` | — | Upload URL expiry timestamp. |
| `variants` | `JSONField` | `[]` | Variant URLs returned by Cloudflare. |
| `cloudflare_metadata` | `JSONField` | `{}` | Metadata returned from Cloudflare payloads. |
| `width` | `PositiveIntegerField` | `None` | Stored image width. |
| `height` | `PositiveIntegerField` | `None` | Stored image height. |
| `format` | `CharField` | `""` | Stored image format. |

### Properties

```python
@property
def is_expired(self) -> bool: ...

@property
def is_uploaded(self) -> bool: ...

@property
def public_url(self) -> str | None: ...

@property
def thumbnail_url(self) -> str | None: ...

@property
def is_ready(self) -> bool: ...
```

### Methods

```python
def get_variant_url(self, variant_name: str) -> str | None: ...
def get_url(self, variant: str = "public") -> str | None: ...
def get_signed_url(self, variant: str = "public", expiry: int = 3600) -> str | None: ...
def update_from_cloudflare_response(self, response_data: dict[str, Any]) -> None: ...
```

`update_from_cloudflare_response()` maps the Cloudflare payload onto the row:
status/`uploaded_at`, `variants`, `cloudflare_metadata` (from `metadata` or, for
GET-image payloads, `meta`), `creator`, `filename`, and `width`/`height`/`format`.

`get_signed_url()` currently falls back to `get_url()` even when `require_signed_urls` is true, because real signing is marked as TODO in the source.

Example:

```python
image = CloudflareImage.objects.get(pk=image_id)
print(image.public_url)
print(image.get_variant_url("thumbnail"))
```

## `ImageUploadLog`

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `image` | `ForeignKey[CloudflareImage]` | — | Parent image record. |
| `event_type` | `CharField` | — | Event name such as `upload_url_created`. |
| `message` | `TextField` | — | Human-readable event summary. |
| `data` | `JSONField` | `{}` | Arbitrary structured event payload. |
| `timestamp` | `DateTimeField` | auto now add | Event creation time. |

Example:

```python
logs = ImageUploadLog.objects.filter(image=image).order_by("-timestamp")
```

These models are the persistence layer behind the service, admin, cleanup command, and `CloudflareImageViewSet`.
