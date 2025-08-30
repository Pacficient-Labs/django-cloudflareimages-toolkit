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
       'DEFAULT_VARIANT': 'public',           # Default image variant for URLs
       'UPLOAD_TIMEOUT': 300,                 # Upload timeout in seconds
       'WEBHOOK_SECRET': 'your-webhook-secret', # For webhook verification
       'CLEANUP_EXPIRED_HOURS': 24,           # Hours before cleaning up expired uploads
       'MAX_FILE_SIZE': 10 * 1024 * 1024,     # Maximum file size (10MB default)
       'ALLOWED_FORMATS': ['jpeg', 'png', 'gif', 'webp'],  # Allowed image formats
       'REQUIRE_SIGNED_URLS': False,          # Whether to require signed URLs
       'DEFAULT_METADATA': {},                # Default metadata for uploads
   }

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
       cloudflare_id = models.CharField(max_length=255, unique=True)
       filename = models.CharField(max_length=255)
       uploaded_at = models.DateTimeField(auto_now_add=True)
       file_size = models.PositiveIntegerField(null=True, blank=True)
       width = models.PositiveIntegerField(null=True, blank=True)
       height = models.PositiveIntegerField(null=True, blank=True)
       format = models.CharField(max_length=10, blank=True)
       variants = models.JSONField(default=dict, blank=True)
       metadata = models.JSONField(default=dict, blank=True)
       is_ready = models.BooleanField(default=False)
       upload_url = models.URLField(blank=True)
       upload_expires_at = models.DateTimeField(null=True, blank=True)

Django Admin Integration
------------------------

The package includes Django admin integration for image management:

.. code-block:: python

   # The admin interface provides:
   # 1. View all uploaded images with thumbnails
   # 2. Search and filter images by various criteria
   # 3. View image metadata and variants
   # 4. Delete images (removes from both Django and Cloudflare)
   # 5. Generate new upload URLs

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
       list_display = ['filename', 'uploaded_at', 'file_size', 'is_ready']
       list_filter = ['is_ready', 'format', 'uploaded_at']
       search_fields = ['filename', 'cloudflare_id']

Image Variants Configuration
----------------------------

Cloudflare Images supports variants for different image sizes and formats:

Creating Variants
~~~~~~~~~~~~~~~~~

Create variants in your Cloudflare Images dashboard or via API:

.. code-block:: python

   from django_cloudflareimages_toolkit.services import CloudflareImagesService
   
   service = CloudflareImagesService()
   
   # Create a thumbnail variant
   service.create_variant(
       variant_id='thumbnail',
       options={
           'fit': 'scale-down',
           'width': 200,
           'height': 200,
       }
   )

Using Variants in Templates
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: html

   <!-- In your Django templates -->
   <img src="{{ image.get_url }}" alt="Original image">
   <img src="{{ image.get_url:'thumbnail' }}" alt="Thumbnail">
   <img src="{{ image.get_url:'avatar' }}" alt="Avatar">

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
           required_signed_urls=True,         # Require signed URLs
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

Configure upload restrictions:

.. code-block:: python

   CLOUDFLARE_IMAGES = {
       # ... other settings
       'MAX_FILE_SIZE': 5 * 1024 * 1024,  # 5MB limit
       'ALLOWED_FORMATS': ['jpeg', 'png'],  # Only JPEG and PNG
       'REQUIRE_SIGNED_URLS': True,        # Require signed URLs for access
   }

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
       
       # Or mock the service entirely
       CLOUDFLARE_IMAGES_MOCK = True

Performance Configuration
-------------------------

Optimize performance with these settings:

.. code-block:: python

   CLOUDFLARE_IMAGES = {
       # ... other settings
       'UPLOAD_TIMEOUT': 60,           # Shorter timeout for faster failures
       'CLEANUP_EXPIRED_HOURS': 1,     # More frequent cleanup
       'DEFAULT_VARIANT': 'optimized', # Use optimized variant by default
   }

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
