Configuration
=============

django-cloudflareimages-toolkit provides flexible configuration options for different deployment scenarios and image management needs.

Required Settings
-----------------

The following settings must be configured in your Django settings file:

.. code-block:: python

   CLOUDFLARE_IMAGES = {
       'ACCOUNT_ID': 'your-cloudflare-account-id',
       'API_TOKEN': 'your-api-token',
       'ACCOUNT_HASH': 'your-account-hash',
   }

Account Information
~~~~~~~~~~~~~~~~~~~

- **ACCOUNT_ID**: Your Cloudflare account ID (found in the right sidebar of any Cloudflare dashboard page)
- **API_TOKEN**: API token with Cloudflare Images permissions
- **ACCOUNT_HASH**: Your account hash for image URLs (found in Images dashboard)

Optional Settings
-----------------

You can customize additional behavior with these optional settings:

.. code-block:: python

   CLOUDFLARE_IMAGES = {
       # Required settings
       'ACCOUNT_ID': 'your-account-id',
       'API_TOKEN': 'your-api-token',
       'ACCOUNT_HASH': 'your-account-hash',

       # Optional settings
       'BASE_URL': 'https://api.cloudflare.com/client/v4',  # API base URL override
       'DEFAULT_EXPIRY_MINUTES': 30,          # Default upload URL expiry (2-360 minutes)
       'REQUIRE_SIGNED_URLS': True,           # Whether uploads require signed URLs
       'DEFAULT_METADATA': {},                # Default metadata (merged under per-request)
       'DEFAULT_CREATOR': None,               # Default Cloudflare "creator" value
       'METADATA_FACTORY': None,              # Dotted path / callable for metadata
       'WEBHOOK_SECRET': 'your-webhook-secret', # For webhook signature verification
       'MAX_FILE_SIZE_MB': 10,                # Maximum file size accessor (MB)
   }

Upload Defaults
~~~~~~~~~~~~~~~

These settings provide defaults for the direct upload service. Any value
passed explicitly to ``cloudflare_service.create_direct_upload_url()`` (or
``get_direct_upload_url()``) overrides the corresponding settings default —
per-request parameters always win.

- **REQUIRE_SIGNED_URLS**: Whether uploads require signed URLs for delivery (default: ``True``)
- **DEFAULT_EXPIRY_MINUTES**: Default upload URL expiry in minutes (default: ``30``)
- **DEFAULT_METADATA**: Default metadata merged *underneath* any per-request metadata; per-request keys win (default: ``{}``)
- **DEFAULT_CREATOR**: Default Cloudflare ``creator`` value applied when no ``creator`` is passed per request (default: ``None``). Pass an explicit empty string (``creator=""``, or ``"creator": ""`` on the REST endpoint) to force an untagged upload that bypasses this default.
- **METADATA_FACTORY**: A dotted import path string, a class, an instance, or any callable, resolved via Django's ``import_string``. Receives the resolved metadata plus upload context and returns the final metadata dict. See :doc:`usage` for the ``ImageMetadataFactory`` API (default: ``None``)

.. note::

   The merge precedence for metadata, lowest to highest, is::

      DEFAULT_METADATA < per-request metadata < factory output

   The factory is trusted server-side code and has the final say, so it can
   augment or override keys supplied by the client.

Environment Variables
---------------------

For security, store sensitive configuration in environment variables:

.. code-block:: bash

   # .env file
   CLOUDFLARE_ACCOUNT_ID=your_account_id_here
   CLOUDFLARE_API_TOKEN=your_api_token_here
   CLOUDFLARE_ACCOUNT_HASH=your_account_hash_here
   CLOUDFLARE_WEBHOOK_SECRET=your_webhook_secret_here

Then reference them in your Django settings:

.. code-block:: python

   import os
   
   CLOUDFLARE_IMAGES = {
       'ACCOUNT_ID': os.getenv('CLOUDFLARE_ACCOUNT_ID'),
       'API_TOKEN': os.getenv('CLOUDFLARE_API_TOKEN'),
       'ACCOUNT_HASH': os.getenv('CLOUDFLARE_ACCOUNT_HASH'),
       'WEBHOOK_SECRET': os.getenv('CLOUDFLARE_WEBHOOK_SECRET'),
   }

CloudflareImage Model Configuration
-----------------------------------

The package uses a Django model to track image uploads and metadata:

Model Fields
~~~~~~~~~~~~

.. code-block:: python

   class CloudflareImage(models.Model):
       id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
       cloudflare_id = models.CharField(max_length=255, unique=True, db_index=True)
       user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.CASCADE, related_name='cloudflare_images')
       filename = models.CharField(max_length=255, blank=True)
       original_filename = models.CharField(max_length=255, blank=True)
       content_type = models.CharField(max_length=100, blank=True)
       file_size = models.PositiveIntegerField(null=True, blank=True)
       upload_url = models.URLField(max_length=500)
       status = models.CharField(max_length=20, choices=ImageUploadStatus.choices,
                                 default=ImageUploadStatus.PENDING)
       require_signed_urls = models.BooleanField(default=True)
       metadata = models.JSONField(default=dict, blank=True)
       creator = models.CharField(max_length=255, blank=True, db_index=True)
       created_at = models.DateTimeField(auto_now_add=True)
       updated_at = models.DateTimeField(auto_now=True)
       uploaded_at = models.DateTimeField(null=True, blank=True)
       expires_at = models.DateTimeField()
       width = models.PositiveIntegerField(null=True, blank=True)
       height = models.PositiveIntegerField(null=True, blank=True)
       format = models.CharField(max_length=10, blank=True)
       variants = models.JSONField(default=list, blank=True)
       cloudflare_metadata = models.JSONField(default=dict, blank=True)

   # ``is_ready``, ``is_uploaded``, ``is_expired``, ``public_url`` and
   # ``thumbnail_url`` are read-only properties on the model, not DB fields.

Django Admin Integration
------------------------

The package includes Django admin integration for image management:

.. code-block:: python

   # The admin interface provides:
   # 1. A thumbnail gallery view of uploads (toggle to table) with status/orphan/usage badges
   # 2. Search and filter images by various criteria (including an Orphaned filter)
   # 3. A "Used by" panel showing which content references each image
   # 4. View image metadata and variants
   # 5. Usage-aware delete (refuses images still in use; removes from Django and Cloudflare)
   # 6. Generate new upload URLs

Custom Admin Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

You can customize the admin interface:

.. code-block:: python

   # admin.py
   from django.contrib import admin
   from django_cloudflareimages_toolkit.admin import CloudflareImageAdmin
   from django_cloudflareimages_toolkit.models import CloudflareImage
   
   # Unregister the default admin
   admin.site.unregister(CloudflareImage)
   
   # Register with custom configuration
   @admin.register(CloudflareImage)
   class CustomCloudflareImageAdmin(CloudflareImageAdmin):
       list_display = ['filename', 'uploaded_at', 'file_size', 'status']
       list_filter = ['status', 'require_signed_urls', 'uploaded_at']
       search_fields = ['filename', 'cloudflare_id']

Maintenance Commands
--------------------

Two management commands keep image data tidy:

.. code-block:: bash

   # Mark expired upload URLs; optionally delete old expired rows
   python manage.py cleanup_expired_images --delete --days 30

   # Delete orphaned (unreferenced) images from Cloudflare + DB
   python manage.py cleanup_expired_images --delete-orphans --orphan-days 30

   # Rebuild the usage registry from your models (run before orphan cleanup)
   python manage.py reconcile_image_usage

See :doc:`usage` and :doc:`api` for the full image usage registry workflow.

Image Variants Configuration
----------------------------

Cloudflare Images supports variants for different image sizes and formats:

Creating Variants
~~~~~~~~~~~~~~~~~

Named variants (e.g. ``thumbnail``, ``avatar``) are defined in your Cloudflare
Images dashboard. Cloudflare returns their delivery URLs on each image, which
the toolkit stores in ``CloudflareImage.variants`` and exposes via helpers:

.. code-block:: python

   image.public_url            # the "public" variant URL
   image.thumbnail_url         # the "thumbnail" variant URL
   image.get_url('avatar')     # any named variant (None until uploaded)

For on-the-fly resizing you can also build flexible-variant URLs without
predefining them (see :doc:`usage` and the transformation template tags).

Using Variants in Templates
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: django

   {% load cloudflare_images %}

   <!-- Named-variant URLs from the model -->
   <img src="{{ image.public_url }}" alt="Public">
   <img src="{{ image.thumbnail_url }}" alt="Thumbnail">

   <!-- On-the-fly transformations via template tags -->
   {% cf_thumbnail image.public_url 200 %}
   {% cf_avatar image.public_url 100 %}

Webhook Configuration
---------------------

Configure webhooks to receive real-time upload notifications:

URL Configuration
~~~~~~~~~~~~~~~~~

Add the webhook URLs to your Django project:

.. code-block:: python

   # urls.py
   from django.urls import path, include
   
   urlpatterns = [
       # ... other patterns
       path('cloudflare-images/', include('django_cloudflareimages_toolkit.urls')),
   ]

Cloudflare Dashboard Setup
~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Go to your Cloudflare Images dashboard
2. Navigate to the Webhooks section
3. Add a new webhook with URL: ``https://yourdomain.com/cloudflare-images/webhook/``
4. Set the webhook secret in your Django settings

Webhook Security
~~~~~~~~~~~~~~~~

The package verifies webhook signatures for security:

.. code-block:: python

   CLOUDFLARE_IMAGES = {
       # ... other settings
       'WEBHOOK_SECRET': 'your-webhook-secret-from-cloudflare',
   }

Field Configuration
-------------------

Configure the CloudflareImageField for your models:

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from django.db import models
   from django_cloudflareimages_toolkit.fields import CloudflareImageField
   
   class Profile(models.Model):
       name = models.CharField(max_length=100)
       avatar = CloudflareImageField()

Advanced Configuration
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   class Product(models.Model):
       name = models.CharField(max_length=100)
       image = CloudflareImageField(
           variants=['thumbnail', 'large'],  # Specific variants to create
           metadata={'category': 'product'},  # Default metadata
           require_signed_urls=True,          # Require signed URLs
       )

Security Configuration
----------------------

API Token Permissions
~~~~~~~~~~~~~~~~~~~~~

Ensure your API token has the minimum required permissions:

- **Cloudflare Images:Edit** - For uploading and managing images
- **Zone:Zone Settings:Read** - For account information (if needed)

Token Security
~~~~~~~~~~~~~~

.. code-block:: python

   # Use different tokens for different environments
   # Production settings
   CLOUDFLARE_IMAGES = {
       'API_TOKEN': os.getenv('CLOUDFLARE_PROD_API_TOKEN'),
       # ... other settings
   }
   
   # Development settings
   CLOUDFLARE_IMAGES = {
       'API_TOKEN': os.getenv('CLOUDFLARE_DEV_API_TOKEN'),
       # ... other settings
   }

Upload Security
~~~~~~~~~~~~~~~

Require signed URLs by default and expose a configurable maximum file size:

.. code-block:: python

   CLOUDFLARE_IMAGES = {
       # ... other settings
       'REQUIRE_SIGNED_URLS': True,  # Require signed URLs for delivery by default
       'MAX_FILE_SIZE_MB': 5,        # Configurable maximum file size accessor (MB)
   }

``REQUIRE_SIGNED_URLS`` is the per-upload default (override per request via
``create_direct_upload_url(require_signed_urls=...)``). ``MAX_FILE_SIZE_MB`` is
read via ``cloudflare_settings.max_file_size_mb`` for your own validation.

Logging Configuration
---------------------

Configure logging to monitor image operations:

.. code-block:: python

   # settings.py
   LOGGING = {
       'version': 1,
       'disable_existing_loggers': False,
       'formatters': {
           'verbose': {
               'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
               'style': '{',
           },
       },
       'handlers': {
           'file': {
               'level': 'INFO',
               'class': 'logging.FileHandler',
               'filename': 'cloudflare_images.log',
               'formatter': 'verbose',
           },
           'console': {
               'level': 'DEBUG',
               'class': 'logging.StreamHandler',
               'formatter': 'verbose',
           },
       },
       'loggers': {
           'django_cloudflareimages_toolkit': {
               'handlers': ['file', 'console'],
               'level': 'INFO',
               'propagate': True,
           },
       },
   }

Testing Configuration
---------------------

For testing environments:

.. code-block:: python

   # settings/test.py
   if 'test' in sys.argv:
       # Use test credentials or mock the service
       CLOUDFLARE_IMAGES = {
           'ACCOUNT_ID': 'test-account-id',
           'API_TOKEN': 'test-api-token',
           'ACCOUNT_HASH': 'test-account-hash',
       }

In tests, mock Cloudflare at the HTTP boundary (for example with the
``responses`` library) rather than monkeypatching the service, so the real
request/response handling is still exercised.

Housekeeping
------------

Keep upload-URL lifetimes short and clean up stale rows:

.. code-block:: python

   CLOUDFLARE_IMAGES = {
       # ... other settings
       'DEFAULT_EXPIRY_MINUTES': 30,  # Upload URLs expire 2-360 minutes out
   }

Expired upload slots are reconciled with the ``cleanup_expired_images``
management command (see :doc:`usage`).

Best Practices
--------------

1. **Environment Separation**: Use different API tokens for dev/staging/production
2. **Secure Storage**: Never commit API tokens to version control
3. **Monitor Usage**: Set up logging to track image operations
4. **Regular Cleanup**: Use the cleanup management command regularly
5. **Variant Strategy**: Plan your image variants based on actual usage
6. **Webhook Security**: Always verify webhook signatures
7. **Error Handling**: Implement proper error handling for upload failures
8. **Testing**: Test image uploads in all environments before deployment
