# Django Cloudflare Images Toolkit

A comprehensive Django toolkit for Cloudflare Images with direct creator upload, advanced image management, transformations, and secure upload workflows.

## Features

- **Direct Creator Upload**: Secure image uploads without exposing API keys to clients
- **Comprehensive Image Management**: Track upload status, metadata, and variants
- **Image Usage Registry (SSOT)**: Automatically tracks *which content references each image*, surfaces orphans, and powers an admin thumbnail gallery
- **Advanced Transformations**: Full support for Cloudflare Images transformations
- **Template Tags**: Easy integration with Django templates
- **RESTful API**: Complete API for image management
- **Webhook Support**: Handle Cloudflare webhook notifications
- **Management Commands**: CLI tools for maintenance and cleanup
- **Type Safety**: Full type hints throughout the codebase
- **Responsive Images**: Built-in support for responsive image delivery

## Installation

### Using uv (Recommended)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create a new project or navigate to existing one
uv init my-project
cd my-project

# Add django-cloudflareimages-toolkit to your project
uv add django-cloudflareimages-toolkit

# Or install in development mode from source
uv add --editable .
```

### Using pip

```bash
pip install django-cloudflareimages-toolkit
```

## Quick Start

### 1. Add to Django Settings

```python
# settings.py
INSTALLED_APPS = [
    # ... your other apps
    'rest_framework',
    'django_cloudflareimages_toolkit',
]

# Cloudflare Images Configuration
CLOUDFLARE_IMAGES = {
    'ACCOUNT_ID': 'your-cloudflare-account-id',      # For API calls
    'ACCOUNT_HASH': 'your-cloudflare-account-hash',  # For delivery URLs (different from ID!)
    'API_TOKEN': 'your-cloudflare-api-token',
    'BASE_URL': 'https://api.cloudflare.com/client/v4',  # Optional
    'DEFAULT_EXPIRY_MINUTES': 30,  # Optional (2-360 minutes)
    'REQUIRE_SIGNED_URLS': True,  # Optional
    'DEFAULT_METADATA': {'env': 'production'},  # Optional: merged under per-request metadata
    'DEFAULT_CREATOR': None,  # Optional: default Cloudflare "creator" value
    'METADATA_FACTORY': None,  # Optional: dotted path to an ImageMetadataFactory (see below)
    'WEBHOOK_SECRET': 'your-webhook-secret',  # Optional
    'MAX_FILE_SIZE_MB': 10,  # Optional
}
# These deployment-time defaults are intended to be env-backed in your project.
# Per-request values always take precedence over the settings defaults.
# Note: ACCOUNT_HASH is found in Cloudflare Images dashboard under "Developer Resources"
# or from any image delivery URL: https://imagedelivery.net/<ACCOUNT_HASH>/...

# REST Framework (if not already configured)
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
```

### 2. Add URL Patterns

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    # ... your other URLs
    path('cloudflare-images/', include('django_cloudflareimages_toolkit.urls')),
]
```

### 3. Run Migrations

```bash
python manage.py makemigrations django_cloudflareimages_toolkit
python manage.py migrate
```

### 4. Django Admin Integration (Optional)

The module includes comprehensive Django admin integration for monitoring and managing images:

```python
# settings.py - Admin is automatically registered when the app is installed
# No additional configuration needed

# To access the admin interface:
# 1. Create a superuser: python manage.py createsuperuser
# 2. Visit /admin/ and navigate to "Cloudflare Images" section
```

## Usage

### API Endpoints

#### Create Upload URL
```bash
POST /cloudflare-images/api/upload-url/
Content-Type: application/json

{
    "metadata": {"type": "avatar", "user_id": "123"},
    "require_signed_urls": true,
    "expiry_minutes": 60,
    "filename": "avatar.jpg",
    "creator": "user-123"
}
```

Response:
```json
{
    "id": "uuid-here",
    "cloudflare_id": "cloudflare-image-id",
    "upload_url": "https://upload.imagedelivery.net/...",
    "expires_at": "2024-01-01T12:00:00Z",
    "status": "pending"
}
```

#### List / Search Images
```bash
GET /cloudflare-images/api/images/
# Filter & search:
GET /cloudflare-images/api/images/?status=uploaded&filename=avatar&creator=user-123
GET /cloudflare-images/api/images/?orphaned=true        # only unreferenced images
GET /cloudflare-images/api/images/?search=logo&ordering=-created_at
GET /cloudflare-images/api/images/?metadata__type=avatar
```

#### Look Up an Image by Cloudflare ID
```bash
GET /cloudflare-images/api/images/by-cloudflare-id/{cloudflare_id}/
```

#### Check Image Status
```bash
POST /cloudflare-images/api/images/{id}/check_status/
```

#### Image Usage (which content references an image)
```bash
GET  /cloudflare-images/api/images/{id}/usages/   # references for one image
GET  /cloudflare-images/api/images/orphans/       # images referenced by nothing
GET  /cloudflare-images/api/usages/               # browse all usage records
```

#### Delete Images (usage-aware, removes from Cloudflare + DB)
```bash
# Refused with HTTP 409 if the image is still referenced by content...
DELETE /cloudflare-images/api/images/{id}/
# ...unless you force it:
DELETE /cloudflare-images/api/images/{id}/?force=true

# Bulk delete by internal id and/or Cloudflare id:
POST /cloudflare-images/api/images/bulk_delete/
{"ids": ["uuid-1"], "cloudflare_ids": ["cf-2"], "force": false}
```

#### Get Image Statistics
```bash
GET /cloudflare-images/api/stats/
```

### Template Tags

Load the template tags in your templates:

```django
{% load cloudflare_images %}
```

#### Basic Image Transformations

```django
<!-- Simple thumbnail -->
{% cf_thumbnail image.public_url 200 %}

<!-- Avatar with transformations -->
{% cf_avatar user.profile_image.public_url 100 %}

<!-- Custom transformations -->
{% cf_image_transform image.public_url width=800 height=600 fit='cover' quality=85 %}

<!-- Hero image -->
{% cf_hero_image banner.public_url 1920 800 %}
```

#### Responsive Images

```django
<!-- Responsive image with srcset -->
{% cf_responsive_img image.public_url "Alt text" "img-responsive" "320,640,1024" %}

<!-- Picture element for different screen sizes -->
{% cf_picture image.public_url "Alt text" "responsive-img" 320 768 1200 %}

<!-- Generate srcset manually -->
<img src="{% cf_responsive_image image.public_url 800 %}"
     srcset="{% cf_srcset image.public_url '320,640,1024,1920' %}"
     sizes="{% cf_sizes 'max-width: 768px:100vw,default:800' %}"
     alt="Responsive image">
```

#### Upload Form

```django
<!-- Simple upload form -->
{% cf_upload_form %}

<!-- Custom upload form -->
{% cf_upload_form "my-upload-form" "custom-class" "Choose File" %}
```

#### Image Gallery

```django
{% cf_image_gallery user_images 4 250 %}
```

### Python API

#### Creating Upload URLs

```python
from django_cloudflareimages_toolkit.services import cloudflare_service

# Create upload URL
image = cloudflare_service.create_direct_upload_url(
    user=request.user,
    metadata={'type': 'product', 'category': 'electronics'},
    require_signed_urls=True,
    expiry_minutes=60,
    creator='user-123',  # Cloudflare "creator" field, persisted + queryable
)

print(f"Upload URL: {image.upload_url}")
print(f"Expires at: {image.expires_at}")
```

Any argument you omit falls back to its settings default (`DEFAULT_METADATA`,
`DEFAULT_CREATOR`, `REQUIRE_SIGNED_URLS`, `DEFAULT_EXPIRY_MINUTES`). To bypass
`DEFAULT_CREATOR` for a single upload, pass an explicit empty string
(`creator=''`, or `"creator": ""` on the REST endpoint). The resolved
`metadata` and `creator` are sent to Cloudflare's
`/images/v2/direct_upload` endpoint and round-tripped onto the local
`CloudflareImage` record, so they are queryable from Django:

```python
CloudflareImage.objects.filter(creator='user-123')
CloudflareImage.objects.filter(metadata__type='product')
```

#### Programmatic metadata (`ImageMetadataFactory`)

For metadata that must be computed at upload time (tenant id, request context,
timestamps, …), register a server-side factory instead of a static
`DEFAULT_METADATA` dict. Subclass `ImageMetadataFactory` and point
`METADATA_FACTORY` at it (a dotted path, class, instance, or any callable):

```python
# myapp/factories.py
from django_cloudflareimages_toolkit import ImageMetadataFactory

class TenantMetadataFactory(ImageMetadataFactory):
    def get_metadata(self, *, metadata, user=None, **context):
        if user is not None:
            metadata['uploaded_by'] = str(user.pk)
        metadata['source'] = 'web'
        return metadata

# settings.py
CLOUDFLARE_IMAGES['METADATA_FACTORY'] = 'myapp.factories.TenantMetadataFactory'
```

The factory receives the already-resolved metadata plus upload context and
returns the final dict. Merge precedence is, lowest to highest:

```
DEFAULT_METADATA  <  per-request metadata  <  factory output
```

Because the factory is trusted server-side code it has the final say and can
both augment and override client-supplied keys.

#### Image Transformations

```python
from django_cloudflareimages_toolkit.transformations import CloudflareImageTransform

# Cloudflare Images (imagedelivery.net) - uses flexible variants
transform = CloudflareImageTransform(image.public_url)
thumbnail_url = (transform
    .width(300)
    .height(300)
    .fit('cover')
    .quality(85)
    .build())
# Result: https://imagedelivery.net/<hash>/<id>/width=300,height=300,fit=cover,quality=85

# Cloudflare Image Resizing (custom domains) - uses /cdn-cgi/image/ format
transform = CloudflareImageTransform("/images/photo.jpg", zone="example.com")
resized_url = transform.width(800).quality(85).build()
# Result: https://example.com/cdn-cgi/image/width=800,quality=85/images/photo.jpg

# Use predefined variants
from django_cloudflareimages_toolkit.transformations import CloudflareImageVariants

avatar_url = CloudflareImageVariants.avatar(image.public_url, 100)
hero_url = CloudflareImageVariants.hero_image(image.public_url, 1920, 800)
thumbnail_url = CloudflareImageVariants.thumbnail(image.public_url, 150)
product_url = CloudflareImageVariants.product_image(image.public_url, 400)
```

#### Checking Image Status

```python
# Check if image is uploaded
if image.is_uploaded:
    print(f"Image available at: {image.public_url}")

# Refresh status from Cloudflare
cloudflare_service.check_image_status(image)
```

#### Registering an already-uploaded image

When a client finishes a direct upload it reports back a `cloudflare_id`. Do
**not** trust that ID by calling
`CloudflareImage.objects.get_or_create(cloudflare_id=<id>)`: the ID may not
exist, may still be a draft (no bytes uploaded yet), or belong to another user,
and `get_or_create` would happily leave a bare local row with no status or
variants.

Use the manager method instead. It verifies the image against Cloudflare first
— confirming it exists and that its draft state is cleared — then creates the
local record populated with status, variants, metadata, and creator:

```python
from django_cloudflareimages_toolkit import (
    CloudflareImage,
    ImageNotFoundError,
    ImageNotReadyError,
    ImageOwnershipError,
)

try:
    image = CloudflareImage.objects.register_uploaded(
        cloudflare_id, user=request.user
    )
except ImageNotFoundError:
    ...  # the ID does not exist in Cloudflare
except ImageNotReadyError:
    ...  # the image exists but is still a draft (upload not completed)
```

`register_uploaded` only creates/returns a local row once Cloudflare confirms a
completed upload, so the resulting record is always trustworthy.

If you set `creator` at upload time to the uploader's identifier, pass
`expected_creator` so a caller can only register *their own* image — the
Cloudflare `creator` must match or `ImageOwnershipError` is raised before any
row is created:

```python
try:
    image = CloudflareImage.objects.register_uploaded(
        cloudflare_id,
        user=request.user,
        expected_creator=str(request.user.pk),
    )
except ImageOwnershipError:
    ...  # the image belongs to a different creator
```

`ImageOwnershipError` is also raised if the `cloudflare_id` is already registered
locally to a *different* user, so `register_uploaded` never hands a caller back
someone else's record — even without `expected_creator`.

### Management Commands

#### Clean Up Expired Images

```bash
# Dry run to see what would be cleaned up
python manage.py cleanup_expired_images --dry-run

# Mark expired images as expired
python manage.py cleanup_expired_images

# Delete old expired images (older than 7 days)
python manage.py cleanup_expired_images --delete --days 7

# Delete orphaned (unreferenced) images older than 30 days from Cloudflare + DB
python manage.py cleanup_expired_images --delete-orphans --orphan-days 30
```

#### Reconcile the Image Usage Registry

Signals keep usage tracking current for ordinary saves/deletes. Bulk operations
(`QuerySet.update()`, `bulk_create`, `loaddata`) bypass signals, so run this to
rebuild the registry and report orphans / unregistered references. It is
idempotent and safe to schedule:

```bash
python manage.py reconcile_image_usage            # rebuild + report
python manage.py reconcile_image_usage --dry-run  # report only, no writes
```

### Django Admin Interface

The module provides a comprehensive Django admin interface for monitoring and managing Cloudflare Images:

#### Features:
- **Image List View**: View all images with status, thumbnails, and key information
- **Gallery View**: A thumbnail-grid view of uploads (toggle to table) with status, orphan, and usage badges
- **Used-by Panel**: See which content references each image, with links to the referencing objects
- **Detailed Image View**: Complete image details with transformation examples
- **Status Management**: Check status, refresh from Cloudflare, mark as expired
- **Bulk Actions**: Perform operations on multiple images at once
- **Upload Logs**: View complete audit trail for each image
- **Statistics Dashboard**: Overview of upload success rates and system health
- **Search & Filtering**: Find images by ID, filename, user, status, or date
- **Image Previews**: Thumbnail previews and full-size image viewing
- **Transformation Examples**: Live examples of different image transformations

#### Admin Actions:
- **Check Status from Cloudflare**: Refresh status for selected images
- **Mark as Expired**: Manually mark images as expired
- **Delete from Cloudflare**: Remove images from Cloudflare and local database
- **Refresh All Pending/Draft**: Update status for all non-final images

#### Access the Admin:
1. Create a superuser: `python manage.py createsuperuser`
2. Visit `/admin/` in your browser
3. Navigate to "Cloudflare Images" section
4. Manage images through the intuitive interface

### Webhooks

Configure webhooks in your Cloudflare dashboard to point to:
```
https://yourdomain.com/cloudflare-images/api/webhook/
```

The webhook endpoint will automatically update image status when uploads complete.

**📋 For detailed webhook setup instructions, see the [Webhook Configuration documentation](https://django-cloudflareimages-toolkit.readthedocs.io/en/latest/webhooks.html)**

This guide includes:
- Step-by-step Cloudflare dashboard configuration
- Django settings and URL configuration
- Security considerations and signature validation
- Troubleshooting common webhook issues
- Local development setup with ngrok

## Advanced Features

### Custom Image Variants

```python
from django_cloudflareimages_toolkit.transformations import CloudflareImageTransform

def create_product_variant(image_url: str, size: int = 400) -> str:
    """Create a product image with white background and border."""
    return (CloudflareImageTransform(image_url)
        .width(size)
        .height(size)
        .fit('pad')
        .background('ffffff')
        .border(2, 'cccccc')
        .quality(90)
        .build())
```

### Responsive Image Sets

```python
from django_cloudflareimages_toolkit.transformations import CloudflareImageUtils

# Generate srcset for responsive images
srcset = CloudflareImageUtils.get_srcset(
    image.public_url, 
    [320, 640, 1024, 1920], 
    quality=85
)

# Generate sizes attribute
sizes = CloudflareImageUtils.get_sizes_attribute({
    'max-width: 768px': 100,  # 100vw on mobile
    'max-width: 1024px': 50,  # 50vw on tablet
    'default': 800  # 800px on desktop
})
```

### Bulk Operations

```python
from django_cloudflareimages_toolkit.models import CloudflareImage

# Bulk status check
images = CloudflareImage.objects.filter(status='pending')
for image in images:
    try:
        cloudflare_service.check_image_status(image)
    except Exception as e:
        print(f"Failed to check {image.cloudflare_id}: {e}")
```

## Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `ACCOUNT_ID` | Required | Your Cloudflare Account ID (for API calls) |
| `ACCOUNT_HASH` | Required | Your Cloudflare Account Hash (for delivery URLs - find in Images dashboard) |
| `API_TOKEN` | Required | Cloudflare API Token with Images permissions |
| `BASE_URL` | `https://api.cloudflare.com/client/v4` | Cloudflare API base URL |
| `DEFAULT_EXPIRY_MINUTES` | `30` | Default expiry time for upload URLs (2-360 minutes) |
| `REQUIRE_SIGNED_URLS` | `True` | Require signed URLs by default |
| `WEBHOOK_SECRET` | `None` | Secret for webhook signature validation |
| `MAX_FILE_SIZE_MB` | `10` | Maximum file size in MB |

## Models

### CloudflareImage

Tracks image uploads and their metadata:

- `cloudflare_id`: Unique Cloudflare image identifier
- `user`: Associated Django user (optional)
- `upload_url`: One-time upload URL
- `status`: Current upload status (pending, draft, uploaded, failed, expired)
- `metadata`: Custom metadata JSON
- `variants`: Available image variants
- `expires_at`: Upload URL expiration time

### ImageUploadLog

Tracks events and changes for debugging:

- `image`: Associated CloudflareImage
- `event_type`: Type of event (upload_url_created, status_checked, etc.)
- `message`: Human-readable message
- `data`: Additional event data

### ImageUsage

Reverse index mapping each image to the content that references it (see
[Image Usage Registry](#image-usage-registry-ssot)):

- `content_type` / `object_id` / `content_object`: the referencing model instance
- `field_name`: the field that holds the reference (e.g. `avatar`, or `manual`)
- `cloudflare_id`: the referenced Cloudflare image ID (source of truth)
- `image`: resolved `CloudflareImage` (null = referenced but unregistered)

## Image Usage Registry (SSOT)

`CloudflareImage` answers *"what has been uploaded"*. The usage registry answers
the other half — *"what content is using each image"* — so admins and site staff
have a single source of truth for both.

**Automatic tracking.** Every model field declared as a `CloudflareImageField` is
auto-discovered. Saving, updating, or deleting such a model keeps an `ImageUsage`
row in sync via signals — no extra code required.

```python
from django_cloudflareimages_toolkit.fields import CloudflareImageField

class Product(models.Model):
    image = CloudflareImageField(blank=True, null=True)

product = Product.objects.create(image="cloudflare-image-id")
# -> an ImageUsage row now links that image to this product
```

**Manual API.** For references the toolkit can't see (an ID kept in a JSON blob,
derived at runtime, etc.):

```python
from django_cloudflareimages_toolkit import register_usage, unregister_usage

register_usage(my_object, "cloudflare-image-id")     # field_name="manual" by default
unregister_usage(my_object)
```

**Reverse lookups.**

```python
image.usages.all()                                          # what uses this image
CloudflareImage.objects.filter(usages__isnull=True)         # orphans (unused)
ImageUsage.objects.filter(image__isnull=True)               # referenced but unregistered
```

**Admin gallery.** The admin image list gains a thumbnail **gallery view** (with
table toggle), status/orphan/usage badges, a "Used by" panel linking to the
referencing objects, and Orphaned/Unregistered filters so staff can see at a
glance what each image is used by.

**Usage-aware deletes (API).** The REST API delete endpoints refuse to delete an
image still referenced by content (HTTP 409) unless `force=true`. The admin's
existing delete actions are not guarded — staff are trusted to consult the
"Used by" panel before deleting.

> Bulk operations bypass signals; run `python manage.py reconcile_image_usage`
> to rebuild the registry (it is idempotent).

## Development

### Setting up with uv

```bash
# Clone the repository
git clone https://github.com/Pacficient-Labs/django-cloudflareimages-toolkit.git
cd django-cloudflareimages-toolkit

# Install dependencies
uv sync

# Install development dependencies
uv sync --group dev

# Run tests
uv run pytest

# Format code
uv run black .
uv run isort .

# Type checking
uv run mypy django_cloudflareimages_toolkit
```

### Running Tests

```bash
# Run all tests (use venv Python directly for reliability)
.venv/bin/python -m pytest

# Run with coverage
.venv/bin/python -m pytest --cov=django_cloudflareimages_toolkit

# Run specific test file
.venv/bin/python -m pytest tests/test_imports.py

# Alternative: use uv run (ensure venv is synced first)
uv sync --extra dev
uv run pytest
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for your changes
5. Run the test suite (`uv run pytest`)
6. Format your code (`uv run black . && uv run isort .`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- Documentation: [https://django-cloudflareimages-toolkit.readthedocs.io/](https://django-cloudflareimages-toolkit.readthedocs.io/)
- Issues: [https://github.com/Pacificient-Labs/django-cloudflareimages-toolkit/issues](https://github.com/Pacificient-Labs/django-cloudflareimages-toolkit/issues)
- Discussions: [https://github.com/Pacificient-Labs/django-cloudflareimages-toolkit/discussions](https://github.com/Pacificient-Labs/django-cloudflareimages-toolkit/discussions)

## Changelog

For the full release history with diff links, see [GitHub Releases](https://github.com/Pacficient-Labs/django-cloudflareimages-toolkit/releases).

### v1.0.13

- **Added**: New "Patterns & Recipes" docs page (`docs/patterns.rst`) with working code for failover/resilience when the Cloudflare Images API is unavailable, and for image-access authorization with role-based permissions and dynamic watermarking. Both are built on the existing service + transformation primitives — the package stays small, the docs show you how to assemble them.

### v1.0.12

- **Metadata-only release.** Corrected Trove classifiers (dropped EOL Django 4.0/4.1/5.0; added 5.1/5.2/6.0 + Python 3.14); promoted Development Status to Production/Stable; added `Typing :: Typed` classifier and shipped the corresponding `py.typed` marker (PEP 561).
- **Added**: `Changelog` and `Release Notes` entries to `[project.urls]` so PyPI's sidebar links straight to GitHub releases.
- **Docs**: Merged the standalone root-level `WEBHOOK_SETUP.md` into `docs/webhooks.rst` (now the single source, rendered on Read the Docs). Read the Docs config bumped to Python 3.12, ubuntu-24.04, and `fail_on_warning: true`.
- **Repo**: Moved `example_usage.py` → `examples/cloudflareimagefield.py` with an `examples/README.md` index.

### v1.0.11

- **Fixed (security)**: `WebhookView.post` previously skipped signature validation when *either* the signature header was absent *or* `WEBHOOK_SECRET` was unset — meaning a caller could omit the `X-Signature` header entirely and bypass authentication on a deployment that thought it was protected. A configured secret now means signatures are **required**; missing-signature returns 401 before the body is parsed.
- **Fixed (observability)**: `WebhookPayloadSerializer.is_valid(raise_exception=True)` raises DRF `ValidationError`, which used to be swallowed by a broad `except Exception` and reported as `500 Internal server error`. Malformed payloads are now `400 Invalid payload`, reserving 5xx for genuinely unexpected processing failures.
- **Added**: Documented status-code matrix for the webhook endpoint (200/400/401/404/500) with the contract for each.
- **Tests**: Five new regression tests in `tests/test_webhook_view.py` covering both fixes. 41/41 tests pass on Django 4.2/5.0/5.1/5.2/6.0.

### v1.0.10

- **Fixed**: Eager settings validation no longer blocks Django startup when `CLOUDFLARE_IMAGES` settings are absent or incomplete in non-production environments.

### v1.0.9

- **Fixed**: Transformation URLs now use correct Cloudflare format (`width=300,height=200` path-based)
- **Fixed**: Added missing `expiry` parameter to direct upload API requests
- **Fixed**: `per_page` max increased to 10000 (was incorrectly 100)
- **Added**: `ACCOUNT_HASH` setting (separate from `ACCOUNT_ID` for delivery URLs)
- **Fixed**: Enum comparison for `ImageUploadStatus` (was comparing string to enum)
- **Added**: `get_variant_url()` method on `CloudflareImage` model
- **Fixed**: Double-slash bug in cdn-cgi URLs for Image Resizing
- **Fixed**: Lazy imports to prevent import-time Django dependency errors

### v1.0.0

- Initial release
- Direct Creator Upload support
- Comprehensive image transformations
- Template tags and filters
- RESTful API
- Webhook support
- Management commands
- Full type safety
