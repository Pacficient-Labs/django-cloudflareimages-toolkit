django-cloudflareimages-toolkit Documentation
==============================================

Django integration for Cloudflare Images API with secure direct upload support.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   configuration
   usage
   webhooks
   api

Overview
--------

django-cloudflareimages-toolkit is a Django package that provides seamless integration with Cloudflare Images. It offers:

* **Direct Creator Upload**: Secure client-side uploads using Cloudflare's Direct Creator method
* **Image Management**: Complete CRUD operations for images
* **Webhook Support**: Real-time image processing notifications
* **Flexible Variants**: Support for Cloudflare's image transformation variants
* **Security First**: Token-based authentication and secure upload URLs
* **Django Integration**: Native Django model fields and admin interface

Quick Start
-----------

Install the package:

.. code-block:: bash

   pip install django-cloudflareimages-toolkit

Add to your Django settings:

.. code-block:: python

   INSTALLED_APPS = [
       # ... other apps
       'django_cloudflareimages_toolkit',
   ]

   # Cloudflare Images configuration
   CLOUDFLARE_IMAGES = {
       'ACCOUNT_ID': 'your-account-id',
       'API_TOKEN': 'your-api-token',
       'ACCOUNT_HASH': 'your-account-hash',
   }

Use in your models:

.. code-block:: python

   from django.db import models
   from django_cloudflareimages_toolkit.fields import CloudflareImageField

   class Profile(models.Model):
       name = models.CharField(max_length=100)
       avatar = CloudflareImageField()

Requirements
------------

* Django 4.2+
* Python 3.10+
* Cloudflare Images account and API token

Features
--------

* **Secure Uploads**: Direct client-side uploads without exposing API credentials
* **Image Variants**: Automatic support for Cloudflare's image transformations
* **Webhook Integration**: Real-time processing status updates
* **Admin Interface**: Django admin integration for image management
* **Cleanup Commands**: Management commands for expired image cleanup
* **Type Safety**: Full type hints and mypy compatibility

Documentation Sections
----------------------

* :doc:`installation` - Installation and setup guide
* :doc:`configuration` - Configuration options and settings
* :doc:`usage` - Usage examples and best practices
* :doc:`api` - Complete API reference

Links
-----

* **PyPI**: https://pypi.org/project/django-cloudflareimages-toolkit/
* **GitHub**: https://github.com/PacNPal/django-cloudflareimages-toolkit
* **Issues**: https://github.com/PacNPal/django-cloudflareimages-toolkit/issues

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
