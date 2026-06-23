---
title: "Getting Started"
description: "Install django-cloudflareimages-toolkit, understand the problem it solves, and get to a first working result."
---

`django-cloudflareimages-toolkit` gives Django applications a structured way to issue Cloudflare Images upload URLs, track upload state locally, and generate delivery URLs and transformations.

## The Problem

- Direct browser uploads are awkward to secure because the browser needs a one-time upload URL, but your Cloudflare API token must stay on the server.
- Cloudflare Images returns useful metadata and variants, but a plain Django project has nowhere to persist upload state, expiry windows, and webhook updates.
- Responsive delivery URLs and variant-specific image URLs are easy to get wrong when you hand-build them in templates or view code.
- Operational tasks such as webhook validation, expired-upload cleanup, and admin inspection usually end up as custom code in every project.

## The Solution

The package splits the problem into focused pieces: `CloudflareImagesService` issues and synchronizes upload URLs, `CloudflareImage` stores lifecycle state, the [image usage registry](/docs/image-usage-registry) tracks which content references each image, `CloudflareImageTransform` builds delivery URLs, and the Django app exposes DRF routes, admin views (including a thumbnail gallery), template tags, and cleanup/reconcile commands around that core.

```python
from django_cloudflareimages_toolkit.services import cloudflare_service

image = cloudflare_service.create_direct_upload_url(
    user=request.user,
    metadata={"kind": "avatar"},
    require_signed_urls=True,
    expiry_minutes=30,
)

print(image.cloudflare_id)
print(image.upload_url)
```

## Installation

<Callout type="info">This is a Python package, not a JavaScript package. The install tabs below use Python package managers instead of npm-style commands.</Callout>

`pip`

```bash
pip install django-cloudflareimages-toolkit
```

`uv`

```bash
uv add django-cloudflareimages-toolkit
```

`poetry`

```bash
poetry add django-cloudflareimages-toolkit
```

`pipx`

```bash
pipx inject your-django-env django-cloudflareimages-toolkit
```

Add the app and REST framework to Django, then define `CLOUDFLARE_IMAGES`:

```python
INSTALLED_APPS = [
    "rest_framework",
    "django_cloudflareimages_toolkit",
]

CLOUDFLARE_IMAGES = {
    "ACCOUNT_ID": "your-cloudflare-account-id",
    "ACCOUNT_HASH": "your-cloudflare-account-hash",
    "API_TOKEN": "your-cloudflare-api-token",
    "BASE_URL": "https://api.cloudflare.com/client/v4",
    "DEFAULT_EXPIRY_MINUTES": 30,
    "REQUIRE_SIGNED_URLS": True,
    "WEBHOOK_SECRET": "optional-webhook-secret",
    "MAX_FILE_SIZE_MB": 10,
}
```

## Quick Start

The smallest working example uses the transformation layer because it is importable even before Django settings are configured. This comes from `django_cloudflareimages_toolkit/transformations.py` and is re-exported from the package root.

```python
from django_cloudflareimages_toolkit import CloudflareImageTransform

base_url = "https://imagedelivery.net/account-hash/demo-image/public"
url = (
    CloudflareImageTransform(base_url)
    .width(300)
    .height(300)
    .fit("cover")
    .quality(85)
    .build()
)

print(url)
```

Expected output:

```text
https://imagedelivery.net/account-hash/demo-image/width=300 height=300 fit=cover quality=85
```

For the full Django workflow, include the package routes and run migrations:

```python
from django.urls import include, path

urlpatterns = [
    path("cloudflare-images/", include("django_cloudflareimages_toolkit.urls")),
]
```

```bash
python manage.py migrate
```

## Key Features

- Django 4.2+ support with Python 3.10+ and typed package metadata in `pyproject.toml`.
- A lazy top-level package export strategy in `django_cloudflareimages_toolkit/__init__.py` so transformation utilities import without a configured Django app.
- A thread-local `requests.Session` in `django_cloudflareimages_toolkit/services.py` so concurrent callers do not share mutable session state.
- Local tracking models and logs in `django_cloudflareimages_toolkit/models.py` for pending, draft, uploaded, failed, and expired uploads, including a queryable `creator` field.
- A pluggable metadata pipeline in `django_cloudflareimages_toolkit/metadata.py` with `DEFAULT_METADATA`, `DEFAULT_CREATOR`, and a `METADATA_FACTORY` extension point that gets the final say on per-upload metadata.
- Safe server-side confirmation of browser uploads via `CloudflareImage.objects.register_uploaded()`, which verifies the image with Cloudflare before persisting a local row.
- Template tags and helper builders in `django_cloudflareimages_toolkit/templatetags/cloudflare_images.py` and `django_cloudflareimages_toolkit/transformations.py` for responsive delivery URLs.
- An image usage registry in `django_cloudflareimages_toolkit/registry.py` that tracks which content references each image, detects orphans, and powers an admin thumbnail gallery.
- Built-in DRF routes, webhook validation, Django admin integration, and an expired-upload cleanup command.

<Cards>
  <Card title="Architecture" href="/docs/architecture">See how the service, models, views, and template tags fit together.</Card>
  <Card title="Core Concepts" href="/docs/direct-upload-lifecycle">Start with the direct upload lifecycle and the tracked image model.</Card>
  <Card title="Image Usage Registry" href="/docs/image-usage-registry">Track which content uses each image, find orphans, and use the admin gallery.</Card>
  <Card title="API Reference" href="/docs/api-reference/cloudflareimagesservice">Jump to exact imports, signatures, settings, and route behavior.</Card>
</Cards>
