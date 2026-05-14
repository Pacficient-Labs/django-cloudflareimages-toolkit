---
title: "CloudflareImagesService"
description: "Reference for the Cloudflare API service class and the module-level cloudflare_service singleton."
---

Source file: `django_cloudflareimages_toolkit/services.py`

Import paths:

```python
from django_cloudflareimages_toolkit.services import (
    CloudflareImagesService,
    cloudflare_service,
)
```

## Constructor

```python
class CloudflareImagesService:
    def __init__(self) -> None: ...
```

The constructor creates a `threading.local()` container. The `session` property lazily creates one `requests.Session` per thread.

## Properties

### `account_id`

```python
@property
def account_id(self) -> str: ...
```

### `api_token`

```python
@property
def api_token(self) -> str: ...
```

### `base_url`

```python
@property
def base_url(self) -> str: ...
```

### `session`

```python
@property
def session(self) -> requests.Session: ...
```

## Methods

### `get_direct_upload_url`

```python
def get_direct_upload_url(
    self,
    user=None,
    custom_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    require_signed_urls: bool | None = None,
    expiry_minutes: int | None = None,
) -> dict[str, str]: ...
```

Returns a compact `{"id": ..., "uploadURL": ...}` dict as an alias over `create_direct_upload_url()`.

### `create_direct_upload_url`

```python
def create_direct_upload_url(
    self,
    user=None,
    custom_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    require_signed_urls: bool | None = None,
    expiry_minutes: int | None = None,
) -> CloudflareImage: ...
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user` | Django model instance \| `None` | `None` | Owner for the created `CloudflareImage` row. |
| `custom_id` | `str \| None` | `None` | Explicit Cloudflare image ID to request. |
| `metadata` | `dict[str, Any] \| None` | `None` | Metadata serialized into the Cloudflare request and stored locally. |
| `require_signed_urls` | `bool \| None` | settings default | Overrides `CLOUDFLARE_IMAGES["REQUIRE_SIGNED_URLS"]`. |
| `expiry_minutes` | `int \| None` | settings default | Clamped to `2..360` minutes before the request is sent. |

Example:

```python
image = cloudflare_service.create_direct_upload_url(
    user=request.user,
    metadata={"kind": "avatar"},
    expiry_minutes=20,
)
```

### `check_image_status`

```python
def check_image_status(self, image: CloudflareImage) -> dict[str, Any]: ...
```

Polls Cloudflare for current status, updates the local row, writes an `ImageUploadLog`, and returns the Cloudflare `result` payload.

### `list_images`

```python
def list_images(self, page: int = 1, per_page: int = 1000) -> dict[str, Any]: ...
```

### `get_image`

```python
def get_image(self, image_id: str) -> dict[str, Any]: ...
```

### `update_image`

```python
def update_image(
    self,
    image_id: str,
    metadata: dict[str, Any] | None = None,
    require_signed_urls: bool | None = None,
) -> dict[str, Any]: ...
```

This updates Cloudflare first, then best-effort updates a matching local `CloudflareImage` row if one exists.

### `delete_image`

```python
def delete_image(self, image: CloudflareImage) -> bool: ...
```

Deletes from Cloudflare, writes an `image_deleted` log row locally, and returns `True` on success.

### `validate_webhook_signature`

```python
def validate_webhook_signature(self, payload: bytes, signature: str) -> bool: ...
```

Accepts either bare hex or `sha256=<hex>` signatures. If `WEBHOOK_SECRET` is not configured, it logs a warning and returns `True`.

### `process_webhook`

```python
def process_webhook(self, payload: dict[str, Any]) -> CloudflareImage | None: ...
```

Looks up the local row by `payload["id"]`, applies `update_from_cloudflare_response()`, writes a log row, and returns the updated image or `None`.

## Error Behavior

Remote request failures raise `CloudflareImagesError`. HTTP success with a Cloudflare response that sets `"success": false` also raises `CloudflareImagesError` with the concatenated Cloudflare error messages.

## Common Pattern

```python
image = cloudflare_service.create_direct_upload_url(user=request.user)
cloudflare_service.check_image_status(image)
cloudflare_service.update_image(image.cloudflare_id metadata={"reviewed": True})
```
