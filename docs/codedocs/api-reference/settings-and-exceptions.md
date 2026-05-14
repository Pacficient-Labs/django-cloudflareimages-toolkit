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
def webhook_secret(self) -> str | None: ...

@property
def max_file_size_mb(self) -> int: ...
```

### Configuration table

| Setting key | Type | Default | Required | Description |
|-------------|------|---------|----------|-------------|
| `ACCOUNT_ID` | `str` | — | Yes | Cloudflare account ID for API calls. |
| `ACCOUNT_HASH` | `str` | — | Yes | Account hash used in delivery URLs. |
| `API_TOKEN` | `str` | — | Yes | Bearer token for Cloudflare API calls. |
| `BASE_URL` | `str` | `https://api.cloudflare.com/client/v4` | No | API base URL override. |
| `DEFAULT_EXPIRY_MINUTES` | `int` | `30` | No | Default upload URL lifetime. |
| `REQUIRE_SIGNED_URLS` | `bool` | `True` | No | Default signed URL requirement flag. |
| `WEBHOOK_SECRET` | `str \| None` | `None` | No | HMAC secret for webhook validation. |
| `MAX_FILE_SIZE_MB` | `int` | `10` | No | Configurable file size limit accessor. |

The required accessors raise `ValueError` when missing.

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
```

The current service implementation raises `CloudflareImagesError` directly for request and Cloudflare response failures, but the derived classes are part of the public surface and can still be used by application code that wants more specific failure categories.
