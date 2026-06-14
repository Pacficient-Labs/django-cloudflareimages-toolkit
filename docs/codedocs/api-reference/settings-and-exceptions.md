---
title: "Settings and Exceptions"
description: "Reference for the CloudflareImagesSettings accessor and the package exception classes."
---

Source files: `django_cloudflareimages_toolkit/settings.py`, `django_cloudflareimages_toolkit/exceptions.py`

## `CloudflareImagesSettings`

Import path:

```python
from django_cloudflareimages_toolkit.settings import (
    CloudflareImagesSettings,
    cloudflare_settings,
)
```

The class reads `django.conf.settings.CLOUDFLARE_IMAGES` dynamically on every property access.

### Properties

```python
@property
def account_id(self) -> str: ...

@property
def account_hash(self) -> str: ...

@property
def api_token(self) -> str: ...

@property
def base_url(self) -> str: ...

@property
def default_expiry_minutes(self) -> int: ...

@property
def require_signed_urls(self) -> bool: ...

@property
def default_metadata(self) -> dict: ...

@property
def default_creator(self) -> str | None: ...

@property
def metadata_factory(self) -> Any: ...

@property
def webhook_secret(self) -> str | None: ...

@property
def max_file_size_mb(self) -> int: ...
```

### Methods

```python
def get_metadata_factory(self) -> Callable[..., dict] | None: ...
```

Resolves `METADATA_FACTORY` to a ready-to-call object (or `None`). A dotted-path
string is imported via `django.utils.module_loading.import_string`, a class is
instantiated, and a plain callable/instance is returned as-is. Raises
`ValueError` if the configured value does not resolve to a callable. See
[Package exports](package-exports.md) for the `ImageMetadataFactory` base class.

### Configuration table

| Setting key | Type | Default | Required | Description |
|-------------|------|---------|----------|-------------|
| `ACCOUNT_ID` | `str` | — | Yes | Cloudflare account ID for API calls. |
| `ACCOUNT_HASH` | `str` | — | Yes | Account hash used in delivery URLs. |
| `API_TOKEN` | `str` | — | Yes | Bearer token for Cloudflare API calls. |
| `BASE_URL` | `str` | `https://api.cloudflare.com/client/v4` | No | API base URL override. |
| `DEFAULT_EXPIRY_MINUTES` | `int` | `30` | No | Default upload URL lifetime. |
| `REQUIRE_SIGNED_URLS` | `bool` | `True` | No | Default signed URL requirement flag. |
| `DEFAULT_METADATA` | `dict` | `{}` | No | Metadata merged underneath per-request metadata (per-request keys win). |
| `DEFAULT_CREATOR` | `str \| None` | `None` | No | Default Cloudflare `creator` value for uploads. Pass `creator=""` per request to bypass it. |
| `METADATA_FACTORY` | dotted path / class / instance / callable | `None` | No | Programmatic upload-metadata factory; see `get_metadata_factory()`. |
| `WEBHOOK_SECRET` | `str \| None` | `None` | No | HMAC secret for webhook validation. |
| `MAX_FILE_SIZE_MB` | `int` | `10` | No | Configurable file size limit accessor. |

The required accessors raise `ValueError` when missing.

Per-request arguments to `create_direct_upload_url` always override the settings
defaults. The metadata resolution order, lowest to highest precedence, is
`DEFAULT_METADATA` < per-request `metadata` < `METADATA_FACTORY` output.

## Exceptions

Import path:

```python
from django_cloudflareimages_toolkit.exceptions import (
    CloudflareImagesError,
    CloudflareImagesAPIError,
    ConfigurationError,
    ValidationError,
    UploadError,
    ImageNotFoundError,
    ImageNotReadyError,
    ImageOwnershipError,
)
```

### `CloudflareImagesError`

```python
class CloudflareImagesError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_data: dict | None = None,
    ) -> None: ...
```

This is the base package exception and stores `message`, `status_code`, and `response_data`.

### Derived exceptions

```python
class CloudflareImagesAPIError(CloudflareImagesError): ...
class ConfigurationError(CloudflareImagesError): ...
class ValidationError(CloudflareImagesError): ...
class UploadError(CloudflareImagesError): ...
class ImageNotFoundError(CloudflareImagesError): ...
class ImageNotReadyError(CloudflareImagesError): ...
class ImageOwnershipError(CloudflareImagesError): ...
```

`ImageNotReadyError` signals that a `cloudflare_id` is real but the upload has
not completed (Cloudflare still reports `draft: true`). `ImageOwnershipError`
signals that a registered image's Cloudflare `creator` does not match the
`expected_creator` passed to `register_uploaded`.

The service raises `CloudflareImagesError` directly for generic request and
Cloudflare response failures. Three cases are now typed: `get_image` (and
therefore `register_uploaded_image`) raises `ImageNotFoundError` on a Cloudflare
404, `register_uploaded_image` raises `ImageNotReadyError` for a still-draft
image, and it raises `ImageOwnershipError` on an `expected_creator` mismatch.
Because all subclass `CloudflareImagesError`, existing
`except CloudflareImagesError` handlers continue to match. The remaining derived
classes are part of the public surface for application code that wants more
specific failure categories.
