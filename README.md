# Django Cloudflare Images Toolkit

A comprehensive Django toolkit for Cloudflare Images with direct creator upload, advanced image management, transformations, and secure upload workflows.

## Features

- **Direct Creator Upload**: Secure image uploads without exposing API keys to clients
- **Comprehensive Image Management**: Track upload status, metadata, and variants
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
    'ACCOUNT_ID': 'your-cloudflare-account-id',
    'API_TOKEN': 'your-cloudflare-api-token',
    'BASE_URL': 'https://api.cloudflare.com/client/v4',  # Optional
    'DEFAULT_EXPIRY_MINUTES': 30,  # Optional
    'REQUIRE_SIGNED_URLS': True,  # Optional
    'WEBHOOK_SECRET': 'your-webhook-secret',  # Optional
    'MAX_FILE_SIZE_MB': 10,  # Optional
}

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
    "filename": "avatar.jpg"
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

#### List Images
```bash
GET /cloudflare-images/api/images/
```

#### Check Image Status
```bash
POST /cloudflare-images/api/images/{id}/check_status/
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
    expiry_minutes=60
)

print(f"Upload URL: {image.upload_url}")
print(f"Expires at: {image.expires_at}")
```

#### Image Transformations

```python
from django_cloudflareimages_toolkit.transformations import CloudflareImageTransform

# Build transformation URL
transform = CloudflareImageTransform(image.public_url)
thumbnail_url = (transform
    .width(300)
    .height(300)
    .fit('cover')
    .quality(85)
    .build())

# Use predefined variants
from django_cloudflareimages_toolkit.transformations import CloudflareImageVariants

avatar_url = CloudflareImageVariants.avatar(image.public_url, 100)
hero_url = CloudflareImageVariants.hero_image(image.public_url, 1920, 800)
```

#### Checking Image Status

```python
# Check if image is uploaded
if image.is_uploaded:
    print(f"Image available at: {image.public_url}")

# Refresh status from Cloudflare
cloudflare_service.check_image_status(image)
```

### Management Commands

#### Clean Up Expired Images

```bash
# Dry run to see what would be cleaned up
python manage.py cleanup_expired_images --dry-run

# Mark expired images as expired
python manage.py cleanup_expired_images

# Delete old expired images (older than 7 days)
python manage.py cleanup_expired_images --delete --days 7
```

### Django Admin Interface

The module provides a comprehensive Django admin interface for monitoring and managing Cloudflare Images:

#### Features:
- **Image List View**: View all images with status, thumbnails, and key information
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
| `ACCOUNT_ID` | Required | Your Cloudflare Account ID |
| `API_TOKEN` | Required | Cloudflare API Token with Images permissions |
| `BASE_URL` | `https://api.cloudflare.com/client/v4` | Cloudflare API base URL |
| `DEFAULT_EXPIRY_MINUTES` | `30` | Default expiry time for upload URLs |
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
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=django_cloudflareimages_toolkit

# Run specific test file
uv run pytest tests/test_services.py
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

### v1.0.0

- Initial release
- Direct Creator Upload support
- Comprehensive image transformations
- Template tags and filters
- RESTful API
- Webhook support
- Management commands
- Full type safety
