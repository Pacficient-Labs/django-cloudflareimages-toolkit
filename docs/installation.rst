Installation
============

Requirements
------------

* Django 4.2+
* Python 3.10+
* Cloudflare Images account and API token

Installing the Package
----------------------

Install django-cloudflareimages-toolkit using pip:

.. code-block:: bash

   pip install django-cloudflareimages-toolkit

Or using uv (recommended):

.. code-block:: bash

   uv add django-cloudflareimages-toolkit

Django Configuration
--------------------

Add ``django_cloudflareimages_toolkit`` to your ``INSTALLED_APPS`` in your Django settings:

.. code-block:: python

   INSTALLED_APPS = [
       # ... other apps
       'django_cloudflareimages_toolkit',
   ]

Database Migration
------------------

Run Django migrations to create the necessary database tables:

.. code-block:: bash

   python manage.py migrate

This will create the ``CloudflareImage`` model table for storing image metadata and upload tracking.

Cloudflare Images Account Setup
-------------------------------

1. Sign up for a Cloudflare account at https://cloudflare.com
2. Enable Cloudflare Images in your dashboard
3. Generate an API token with Images permissions
4. Note your Account ID and Account Hash from the Images dashboard

Required Settings
-----------------

Configure the following settings in your Django settings file:

.. code-block:: python

   CLOUDFLARE_IMAGES = {
       'ACCOUNT_ID': 'your-cloudflare-account-id',
       'API_TOKEN': 'your-api-token',
       'ACCOUNT_HASH': 'your-account-hash',
   }

Environment Variables
---------------------

It's recommended to store sensitive configuration in environment variables:

.. code-block:: bash

   # .env file
   CLOUDFLARE_ACCOUNT_ID=your_account_id_here
   CLOUDFLARE_API_TOKEN=your_api_token_here
   CLOUDFLARE_ACCOUNT_HASH=your_account_hash_here

Then in your Django settings:

.. code-block:: python

   import os
   
   CLOUDFLARE_IMAGES = {
       'ACCOUNT_ID': os.getenv('CLOUDFLARE_ACCOUNT_ID'),
       'API_TOKEN': os.getenv('CLOUDFLARE_API_TOKEN'),
       'ACCOUNT_HASH': os.getenv('CLOUDFLARE_ACCOUNT_HASH'),
   }

Optional Settings
-----------------

You can customize additional settings:

.. code-block:: python

   CLOUDFLARE_IMAGES = {
       # Required settings
       'ACCOUNT_ID': 'your-account-id',
       'API_TOKEN': 'your-api-token',
       'ACCOUNT_HASH': 'your-account-hash',
       
       # Optional settings
       'BASE_URL': 'https://api.cloudflare.com/client/v4',  # Cloudflare API base URL
       'WEBHOOK_SECRET': 'your-webhook-secret',  # For webhook signature verification
       'MAX_FILE_SIZE_MB': 10,       # Accessor only (cloudflare_settings.max_file_size_mb); not auto-enforced

       # Upload defaults (per-request parameters override these)
       'REQUIRE_SIGNED_URLS': True,  # Whether uploads require signed URLs
       'DEFAULT_EXPIRY_MINUTES': 30, # Default upload URL expiry (minutes, 2-360)
       'DEFAULT_METADATA': {},       # Default metadata merged under per-request metadata
       'DEFAULT_CREATOR': None,      # Default Cloudflare "creator" value
       'METADATA_FACTORY': None,     # Dotted path / class / instance / callable for metadata

       # Optional: serve images from an alternate domain instead of imagedelivery.net
       'DELIVERY_URL': None,                             # e.g. 'images.example.com'
       'DELIVERY_PATH_PREFIX': 'cdn-cgi/imagedelivery',  # '' for a Worker proxy
       'DELIVERY_INCLUDE_ACCOUNT_HASH': True,            # False for a Worker proxy
   }

The upload defaults (``REQUIRE_SIGNED_URLS``, ``DEFAULT_EXPIRY_MINUTES``,
``DEFAULT_METADATA``, ``DEFAULT_CREATOR``, ``METADATA_FACTORY``) provide
fallbacks for the direct upload service. Any value passed explicitly per
request overrides the corresponding settings default. See
:doc:`configuration` for the full reference.

Webhook Configuration (Optional)
--------------------------------

To receive real-time upload notifications, configure webhooks:

1. Add webhook URLs to your Django URLs:

.. code-block:: python

   # urls.py
   from django.urls import path, include
   
   urlpatterns = [
       # ... other patterns
       path('cloudflare-images/', include('django_cloudflareimages_toolkit.urls')),
   ]

2. Configure the webhook endpoint in Cloudflare Images dashboard:

.. code-block:: text

   Webhook URL: https://yourdomain.com/cloudflare-images/api/webhook/

Verification
------------

To verify your installation is working correctly, you can test the API connection:

.. code-block:: python

   from django_cloudflareimages_toolkit.services import CloudflareImagesService
   
   try:
       service = CloudflareImagesService()
       # Test API connection by listing images
       images = service.list_images()
       print("API connection successful!")
   except Exception as e:
       print(f"Error connecting to Cloudflare Images API: {e}")

Test Direct Upload
------------------

You can test the direct upload functionality:

.. code-block:: python

   from django_cloudflareimages_toolkit.services import CloudflareImagesService
   
   try:
       service = CloudflareImagesService()
       upload_url = service.get_direct_upload_url()
       print(f"Direct upload URL generated: {upload_url['uploadURL']}")
   except Exception as e:
       print(f"Error generating upload URL: {e}")

Next Steps
----------

* Configure your :doc:`configuration` settings
* Learn about :doc:`usage` patterns and model fields
* Review the complete :doc:`api` reference
