---
title: "Package Exports"
description: "See the package-level imports, lazy loading behavior, and primary import paths exposed by django_cloudflareimages_toolkit."
---

Source file: `django_cloudflareimages_toolkit/__init__.py`

The package root is intentionally usable before Django is configured. It eagerly exports transformation helpers and lazily resolves Django-dependent symbols through `__getattr__(name)`.

## Exact Exports

```python
from django_cloudflareimages_toolkit import (
    CloudflareImageTransform,
    CloudflareImageVariants,
    CloudflareImageUtils,
    ImageMetadataFactory,
    CloudflareImage,
    ImageUploadLog,
    ImageUploadStatus,
    cloudflare_service,
    CloudflareImageField,
    CloudflareImageWidget,
    CloudflareImagesError,
    CloudflareImagesAPIError,
    ConfigurationError,
    ValidationError,
    UploadError,
    ImageNotFoundError,
    ImageNotReadyError,
)
```

Top-level metadata:

```python
__version__ = "1.1.0"
__author__ = "PacNPal"
```

## `ImageMetadataFactory`

Source file: `django_cloudflareimages_toolkit/metadata.py`

Base class for building upload metadata programmatically. Subclass it and point
`CLOUDFLARE_IMAGES["METADATA_FACTORY"]` at the subclass (a dotted path, class,
instance, or any callable). It receives the already-resolved metadata
(`DEFAULT_METADATA` merged with the per-request metadata) plus upload context and
returns the final metadata dict sent to Cloudflare and persisted. As trusted
server-side code it has the final say (precedence:
`DEFAULT_METADATA` < per-request metadata < factory output).

```python
from django_cloudflareimages_toolkit import ImageMetadataFactory

class TenantMetadataFactory(ImageMetadataFactory):
    def get_metadata(self, *, metadata, user=None, custom_id=None, creator=None, **context):
        if user is not None:
            metadata["uploaded_by"] = str(user.pk)
        metadata["source"] = "web"
        return metadata
```

Instances are callable (`__call__` delegates to `get_metadata`). It is
Django-independent and exported eagerly from the package root.

## Lazy Import Contract

`CloudflareImageTransform`, `CloudflareImageVariants`, `CloudflareImageUtils`, and `ImageMetadataFactory` are imported directly because they do not depend on Django settings or the ORM. Everything else is mapped by name in `__getattr__`:

```python
def __getattr__(name):
    ...
```

That mapping points to:

- `django_cloudflareimages_toolkit.models`
- `django_cloudflareimages_toolkit.services`
- `django_cloudflareimages_toolkit.fields`
- `django_cloudflareimages_toolkit.widgets`
- `django_cloudflareimages_toolkit.exceptions`

If you are writing reusable Django code, importing from the explicit module path is still clearer:

```python
from django_cloudflareimages_toolkit.services import cloudflare_service
from django_cloudflareimages_toolkit.models import CloudflareImage
from django_cloudflareimages_toolkit.transformations import CloudflareImageTransform
```

Use the root import when convenience matters and explicit module imports when you want call sites to show which subsystem is in use.

## Recommended Import Strategy

For application code, a practical split is:

- import from `django_cloudflareimages_toolkit` when you only need the Django-independent transformation helpers
- import from the explicit module path for service, model, field, widget, and exception code
- reserve wildcard or broad root imports for REPL sessions and small scripts

That advice follows the structure of the source. The package root is primarily a compatibility and ergonomics layer, not a place where new implementation logic lives. The actual behavior is still defined in the underlying modules, so explicit imports make stack traces, mocks, and code search easier to follow.

Example:

```python
from django_cloudflareimages_toolkit import CloudflareImageTransform
from django_cloudflareimages_toolkit.models import CloudflareImage
from django_cloudflareimages_toolkit.services import cloudflare_service
```

## Failure Mode

If you access a name that is not in the lazy import mapping or the eager transformation exports, `__getattr__` raises a normal `AttributeError`. That means typo detection behaves like a regular Python module instead of silently returning `None` or triggering a broad import side effect.

```python
from django_cloudflareimages_toolkit import CloudflareImageTransform

url = CloudflareImageTransform(base_url).width(300).build()
```
