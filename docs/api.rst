API Reference
=============

This section provides detailed documentation for all classes, methods, and functions in django-cloudflareimages-toolkit.

CloudflareImagesService Class
-----------------------------

.. autoclass:: django_cloudflareimages_toolkit.services.CloudflareImagesService
   :members:
   :undoc-members:
   :show-inheritance:

The main service class for interacting with Cloudflare Images API.

get_direct_upload_url Method
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. automethod:: django_cloudflareimages_toolkit.services.CloudflareImagesService.get_direct_upload_url

**Parameters:**

* ``metadata`` (dict, optional): Custom metadata to attach to the image
* ``require_signed_urls`` (bool, optional): Whether to require signed URLs for access

**Returns:** dict with 'id' and 'uploadURL' keys

**Raises:**

* ``CloudflareImagesAPIError``: When the API request fails
* ``ConfigurationError``: When configuration is missing or invalid

**Example:**

.. code-block:: python

   from django_cloudflareimages_toolkit.services import CloudflareImagesService
   
   service = CloudflareImagesService()
   upload_data = service.get_direct_upload_url(
       metadata={'category': 'profile', 'user_id': '123'}
   )
   print(f"Upload URL: {upload_data['uploadURL']}")

list_images Method
~~~~~~~~~~~~~~~~~~

.. automethod:: django_cloudflareimages_toolkit.services.CloudflareImagesService.list_images

**Parameters:**

* ``page`` (int, optional): Page number for pagination (default: 1)
* ``per_page`` (int, optional): Number of images per page (default: 50, max: 100)

**Returns:** dict with pagination info and list of images

**Example:**

.. code-block:: python

   images = service.list_images(page=1, per_page=20)
   for image in images['result']['images']:
       print(f"Image ID: {image['id']}")

get_image Method
~~~~~~~~~~~~~~~~

.. automethod:: django_cloudflareimages_toolkit.services.CloudflareImagesService.get_image

**Parameters:**

* ``image_id`` (str, required): Cloudflare image ID

**Returns:** dict with image details

**Example:**

.. code-block:: python

   image_details = service.get_image('your-image-id')
   print(f"Image URL: {image_details['result']['variants'][0]}")

delete_image Method
~~~~~~~~~~~~~~~~~~~

.. automethod:: django_cloudflareimages_toolkit.services.CloudflareImagesService.delete_image

**Parameters:**

* ``image_id`` (str, required): Cloudflare image ID

**Returns:** dict with success status

**Example:**

.. code-block:: python

   result = service.delete_image('your-image-id')
   if result['success']:
       print("Image deleted successfully")

update_image Method
~~~~~~~~~~~~~~~~~~~

.. automethod:: django_cloudflareimages_toolkit.services.CloudflareImagesService.update_image

**Parameters:**

* ``image_id`` (str, required): Cloudflare image ID
* ``metadata`` (dict, optional): New metadata for the image
* ``require_signed_urls`` (bool, optional): Whether to require signed URLs

**Returns:** dict with updated image details

**Example:**

.. code-block:: python

   updated = service.update_image(
       'your-image-id',
       metadata={'updated': True, 'category': 'featured'}
   )

CloudflareImage Model
---------------------

.. autoclass:: django_cloudflareimages_toolkit.models.CloudflareImage
   :members:
   :undoc-members:
   :show-inheritance:

Django model for tracking Cloudflare Images.

**Fields:**

* ``cloudflare_id`` (CharField): Unique Cloudflare image ID (max 255 characters)
* ``filename`` (CharField): Original filename (max 255 characters)
* ``uploaded_at`` (DateTimeField): Timestamp when image was uploaded
* ``file_size`` (PositiveIntegerField): File size in bytes (optional)
* ``width`` (PositiveIntegerField): Image width in pixels (optional)
* ``height`` (PositiveIntegerField): Image height in pixels (optional)
* ``format`` (CharField): Image format (jpeg, png, gif, webp) (max 10 characters)
* ``variants`` (JSONField): Available image variants
* ``metadata`` (JSONField): Custom metadata
* ``is_ready`` (BooleanField): Whether image processing is complete
* ``upload_url`` (URLField): Direct upload URL (temporary)
* ``upload_expires_at`` (DateTimeField): When upload URL expires

**Methods:**

get_url Method
~~~~~~~~~~~~~~

.. automethod:: django_cloudflareimages_toolkit.models.CloudflareImage.get_url

**Parameters:**

* ``variant`` (str, optional): Image variant name (default: 'public')

**Returns:** str - Full image URL

**Example:**

.. code-block:: python

   image = CloudflareImage.objects.get(cloudflare_id='your-id')
   original_url = image.get_url()
   thumbnail_url = image.get_url('thumbnail')

get_signed_url Method
~~~~~~~~~~~~~~~~~~~~~

.. automethod:: django_cloudflareimages_toolkit.models.CloudflareImage.get_signed_url

**Parameters:**

* ``variant`` (str, optional): Image variant name
* ``expiry`` (int, optional): URL expiry time in seconds

**Returns:** str - Signed image URL

**Example:**

.. code-block:: python

   # Get signed URL that expires in 1 hour
   signed_url = image.get_signed_url('thumbnail', expiry=3600)

is_expired Property
~~~~~~~~~~~~~~~~~~~

.. automethod:: django_cloudflareimages_toolkit.models.CloudflareImage.is_expired

**Returns:** bool - True if upload URL has expired

**Example:**

.. code-block:: python

   if image.is_expired:
       print("Upload URL has expired")

CloudflareImageField
--------------------

.. autoclass:: django_cloudflareimages_toolkit.fields.CloudflareImageField
   :members:
   :undoc-members:
   :show-inheritance:

Django model field for Cloudflare Images integration.

**Parameters:**

* ``variants`` (list, optional): List of variant names to create
* ``metadata`` (dict, optional): Default metadata for uploads
* ``require_signed_urls`` (bool, optional): Whether to require signed URLs
* ``max_file_size`` (int, optional): Maximum file size in bytes
* ``allowed_formats`` (list, optional): List of allowed image formats

**Example:**

.. code-block:: python

   from django.db import models
   from django_cloudflareimages_toolkit.fields import CloudflareImageField
   
   class Product(models.Model):
       name = models.CharField(max_length=100)
       image = CloudflareImageField(
           variants=['thumbnail', 'large'],
           metadata={'category': 'product'},
           max_file_size=5 * 1024 * 1024,  # 5MB
           allowed_formats=['jpeg', 'png']
       )

CloudflareImageWidget
---------------------

.. autoclass:: django_cloudflareimages_toolkit.widgets.CloudflareImageWidget
   :members:
   :undoc-members:
   :show-inheritance:

Django form widget for handling Cloudflare image uploads with JavaScript-based upload functionality.

Django Admin Integration
------------------------

.. autoclass:: django_cloudflareimages_toolkit.admin.CloudflareImageAdmin
   :members:
   :undoc-members:
   :show-inheritance:

Django admin interface for managing Cloudflare Images.

**Features:**

* List view with image previews and metadata
* Search functionality by filename and Cloudflare ID
* Filtering by upload status, format, and date
* Bulk delete operations
* Image detail view with full metadata

**Admin Actions:**

* ``delete_selected_images``: Delete images from both Django and Cloudflare
* ``refresh_image_metadata``: Refresh metadata from Cloudflare API
* ``generate_upload_urls``: Generate new upload URLs for failed uploads

**Example Customization:**

.. code-block:: python

   from django.contrib import admin
   from django_cloudflareimages_toolkit.admin import CloudflareImageAdmin
   from django_cloudflareimages_toolkit.models import CloudflareImage
   
   @admin.register(CloudflareImage)
   class CustomCloudflareImageAdmin(CloudflareImageAdmin):
       list_display = ['filename', 'uploaded_at', 'file_size', 'is_ready', 'image_preview']
       list_filter = ['is_ready', 'format', 'uploaded_at']

Webhook Views
-------------

.. autofunction:: django_cloudflareimages_toolkit.views.cloudflare_webhook

Handles Cloudflare Images webhook notifications.

**URL Pattern:**

.. code-block:: python

   path('webhook/', cloudflare_webhook, name='cloudflare_webhook')

**Webhook Events:**

* ``upload.complete``: Image upload and processing completed
* ``upload.failed``: Image upload failed
* ``image.deleted``: Image was deleted

**Example:**

.. code-block:: python

   # urls.py
   from django.urls import path, include
   
   urlpatterns = [
       path('cloudflare-images/', include('django_cloudflareimages_toolkit.urls')),
   ]

Management Commands
-------------------

cleanup_expired_images Command
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: django_cloudflareimages_toolkit.management.commands.cleanup_expired_images.Command
   :members:
   :undoc-members:

Cleans up expired upload URLs and unused images.

**Options:**

* ``--days`` (int): Number of days to consider for cleanup (default: 1)
* ``--dry-run``: Show what would be deleted without actually deleting
* ``--force``: Skip confirmation prompts

**Example:**

.. code-block:: bash

   # Clean up images older than 7 days
   python manage.py cleanup_expired_images --days 7
   
   # Dry run to see what would be deleted
   python manage.py cleanup_expired_images --dry-run

App Configuration
-----------------

.. autoclass:: django_cloudflareimages_toolkit.apps.DjangoCloudflareimagesToolkitConfig
   :members:
   :undoc-members:
   :show-inheritance:

Django app configuration class.

**Attributes:**

* ``default_auto_field``: Specifies BigAutoField as default primary key
* ``name``: App name for Django's app registry
* ``verbose_name``: Human-readable app name

Exception Classes
-----------------

CloudflareImagesAPIError
~~~~~~~~~~~~~~~~~~~~~~~~

.. autoexception:: django_cloudflareimages_toolkit.exceptions.CloudflareImagesAPIError

Raised when Cloudflare Images API requests fail.

**Common Causes:**

* Network connectivity issues
* Invalid API credentials
* Rate limiting
* Server errors
* Invalid image data

**Example:**

.. code-block:: python

   try:
       service = CloudflareImagesService()
       upload_data = service.get_direct_upload_url()
   except CloudflareImagesAPIError as e:
       print(f"API error: {e}")

ConfigurationError
~~~~~~~~~~~~~~~~~~

.. autoexception:: django_cloudflareimages_toolkit.exceptions.ConfigurationError

Raised when configuration is missing or invalid.

**Common Causes:**

* Missing required settings
* Invalid account credentials
* Malformed configuration data

**Example:**

.. code-block:: python

   try:
       service = CloudflareImagesService()
   except ConfigurationError as e:
       print(f"Configuration error: {e}")

ValidationError
~~~~~~~~~~~~~~~

.. autoexception:: django_cloudflareimages_toolkit.exceptions.ValidationError

Raised when image data validation fails.

**Common Causes:**

* Invalid image format
* File size exceeds limits
* Missing required metadata

**Example:**

.. code-block:: python

   try:
       field = CloudflareImageField(allowed_formats=['jpeg'])
       # Validation occurs during model save
   except ValidationError as e:
       print(f"Validation error: {e}")

Utility Functions
-----------------

Image URL Generation
~~~~~~~~~~~~~~~~~~~~

.. autofunction:: django_cloudflareimages_toolkit.utils.generate_image_url

Generates Cloudflare Images URL.

**Parameters:**

* ``account_hash`` (str): Cloudflare account hash
* ``image_id`` (str): Image ID
* ``variant`` (str, optional): Variant name (default: 'public')

**Returns:** str - Full image URL

**Example:**

.. code-block:: python

   from django_cloudflareimages_toolkit.utils import generate_image_url
   
   url = generate_image_url('account-hash', 'image-id', 'thumbnail')

Signed URL Generation
~~~~~~~~~~~~~~~~~~~~~

.. autofunction:: django_cloudflareimages_toolkit.utils.generate_signed_url

Generates signed URL for private images.

**Parameters:**

* ``base_url`` (str): Base image URL
* ``signing_key`` (str): URL signing key
* ``expiry`` (int, optional): Expiry time in seconds

**Returns:** str - Signed URL

**Example:**

.. code-block:: python

   from django_cloudflareimages_toolkit.utils import generate_signed_url
   
   signed_url = generate_signed_url(base_url, signing_key, expiry=3600)

Configuration Helpers
~~~~~~~~~~~~~~~~~~~~~

.. autofunction:: django_cloudflareimages_toolkit.utils.get_cloudflare_config

Retrieves Cloudflare Images configuration from Django settings.

**Returns:** dict - Configuration dictionary

**Example:**

.. code-block:: python

   from django_cloudflareimages_toolkit.utils import get_cloudflare_config
   
   config = get_cloudflare_config()
   print(f"Account ID: {config['ACCOUNT_ID']}")

Webhook Verification
~~~~~~~~~~~~~~~~~~~~

.. autofunction:: django_cloudflareimages_toolkit.utils.verify_webhook_signature

Verifies Cloudflare webhook signature.

**Parameters:**

* ``payload`` (bytes): Webhook payload
* ``signature`` (str): Webhook signature header
* ``secret`` (str): Webhook secret

**Returns:** bool - True if signature is valid

**Example:**

.. code-block:: python

   from django_cloudflareimages_toolkit.utils import verify_webhook_signature
   
   is_valid = verify_webhook_signature(request.body, signature, secret)

Constants and Settings
----------------------

**Default Settings:**

.. code-block:: python

   # Default configuration keys
   CLOUDFLARE_IMAGES_DEFAULTS = {
       'DEFAULT_VARIANT': 'public',
       'UPLOAD_TIMEOUT': 300,
       'CLEANUP_EXPIRED_HOURS': 24,
       'MAX_FILE_SIZE': 10 * 1024 * 1024,  # 10MB
       'ALLOWED_FORMATS': ['jpeg', 'png', 'gif', 'webp'],
       'REQUIRE_SIGNED_URLS': False,
   }

**API Endpoints:**

.. code-block:: python

   CLOUDFLARE_IMAGES_API_BASE = 'https://api.cloudflare.com/client/v4'
   CLOUDFLARE_IMAGES_DELIVERY_BASE = 'https://imagedelivery.net'

Migration Support
-----------------

The package includes Django migrations for database schema management:

**Initial Migration (0001_initial.py):**

* Creates CloudflareImage model table
* Sets up indexes for performance
* Creates constraints for data integrity

**Migration Commands:**

.. code-block:: bash

   # Apply migrations
   python manage.py migrate django_cloudflareimages_toolkit
   
   # Create new migration (if you modify models)
   python manage.py makemigrations django_cloudflareimages_toolkit

Testing Utilities
-----------------

Mock Service
~~~~~~~~~~~~

For testing purposes, you can mock the CloudflareImagesService:

.. code-block:: python

   from unittest.mock import patch, MagicMock
   from django.test import TestCase
   
   class MyTestCase(TestCase):
       @patch('django_cloudflareimages_toolkit.services.CloudflareImagesService')
       def test_image_upload(self, mock_service):
           mock_instance = MagicMock()
           mock_service.return_value = mock_instance
           mock_instance.get_direct_upload_url.return_value = {
               'id': 'test-id',
               'uploadURL': 'https://test-upload-url.com'
           }
           
           # Your test code here

Test Image Factory
~~~~~~~~~~~~~~~~~~

Create test images for testing:

.. code-block:: python

   from django_cloudflareimages_toolkit.models import CloudflareImage
   
   def create_test_image(**kwargs):
       defaults = {
           'cloudflare_id': 'test-image-id',
           'filename': 'test.jpg',
           'is_ready': True,
           'file_size': 1024,
           'width': 800,
           'height': 600,
           'format': 'jpeg'
       }
       defaults.update(kwargs)
       return CloudflareImage.objects.create(**defaults)

Version Information
-------------------

.. autodata:: django_cloudflareimages_toolkit.__version__

Current package version string.

**Example:**

.. code-block:: python

   import django_cloudflareimages_toolkit
   print(f"Package version: {django_cloudflareimages_toolkit.__version__}")

Logging
-------

The package uses Python's standard logging module with the logger name ``django_cloudflareimages_toolkit``.

**Log Levels:**

* ``DEBUG``: Detailed API request/response information
* ``INFO``: Successful operations and image processing updates
* ``WARNING``: Recoverable errors and fallback usage
* ``ERROR``: Failed operations and API errors
* ``CRITICAL``: System-level failures

**Example Configuration:**

.. code-block:: python

   import logging
   
   # Configure logging for the package
   logging.getLogger('django_cloudflareimages_toolkit').setLevel(logging.INFO)
   
   # Example log output
   logger = logging.getLogger('django_cloudflareimages_toolkit')
   logger.info("Image uploaded successfully: %s", image_id)

Type Hints
----------

The package includes comprehensive type hints for better IDE support and type checking:

.. code-block:: python

   from typing import Dict, List, Optional, Union
   from django_cloudflareimages_toolkit.services import CloudflareImagesService
   
   service: CloudflareImagesService = CloudflareImagesService()
   upload_data: Dict[str, str] = service.get_direct_upload_url()
   images: Dict[str, Union[List, Dict]] = service.list_images()
