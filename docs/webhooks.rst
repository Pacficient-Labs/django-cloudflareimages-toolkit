Webhook Configuration
=====================

This guide explains how to configure webhooks in your Cloudflare dashboard
to automatically update image status when uploads complete, and documents
the request/response contract that ``WebhookView`` enforces on the
Django side.

.. note::
   The signature-validation gate is **enforced** when
   ``CLOUDFLARE_IMAGES["WEBHOOK_SECRET"]`` is set: requests without a
   valid signature header are rejected before the body is parsed. See
   `Response Codes`_ below for the full status-code matrix.

What are Webhooks?
------------------

Webhooks allow Cloudflare to automatically notify your Django application when image uploads are completed or failed. 

.. note::
   Webhooks are currently only supported for direct creator uploads.

Step-by-Step Webhook Configuration
----------------------------------

1. Access Cloudflare Dashboard
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Go to `https://dash.cloudflare.com/ <https://dash.cloudflare.com/>`_
2. Log in to your Cloudflare account
3. Select your account

2. Navigate to Notifications
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. In the left sidebar, click on **"Notifications"**
2. Click on **"Destinations"**

3. Create Webhook Destination
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. From the **Webhooks** card, select **"Create"**
2. Fill in the webhook details:
   
   - **Name**: Give your webhook a descriptive name (e.g., "Django Images Webhook")
   - **URL**: ``https://yourdomain.com/cloudflare-images/api/webhook/``
   - **Secret** (Optional but recommended): Enter your webhook secret if configured

3. Click **"Save and Test"**
4. The new webhook will appear in the **Webhooks** card

4. Create Notification
~~~~~~~~~~~~~~~~~~~~~~

1. Go to **"Notifications"** > **"All Notifications"**
2. Click **"Add"**
3. Under the list of products, locate **"Images"** and select **"Select"**
4. Configure the notification:
   
   - **Name**: Give your notification a descriptive name
   - **Description**: Optional description
   - **Webhooks**: Select the webhook you created in step 3

5. Click **"Save"**

5. Webhook Events
~~~~~~~~~~~~~~~~~

The webhook will be triggered for these events:

- ✅ **Image Upload Complete** - When a direct creator upload succeeds
- ✅ **Image Upload Failed** - When a direct creator upload fails

.. important::
   Webhooks are only triggered for **direct creator uploads**, not for regular API uploads.

Django Configuration
--------------------

End-to-end Django setup is five steps. Run them in order on a fresh
project; each step is independent on a project that already has the
toolkit installed.

Step 1: Install the package
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   pip install django-cloudflareimages-toolkit

Then add ``"django_cloudflareimages_toolkit"`` to ``INSTALLED_APPS``
and run ``python manage.py migrate`` so the ``CloudflareImage`` and
``ImageUploadLog`` tables are created. The webhook view writes status
changes into these tables.

Step 2: Configure the webhook secret
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generate a high-entropy secret (e.g. ``python -c 'import secrets;
print(secrets.token_urlsafe(32))'``) and store it in your settings.
The same value must be entered in the Cloudflare dashboard in step 5.

.. code-block:: python

   # settings.py
   import os

   CLOUDFLARE_IMAGES = {
       "ACCOUNT_ID": os.environ["CLOUDFLARE_ACCOUNT_ID"],
       "API_TOKEN":  os.environ["CLOUDFLARE_API_TOKEN"],
       "WEBHOOK_SECRET": os.environ["CLOUDFLARE_WEBHOOK_SECRET"],
   }

.. important::

   Setting ``WEBHOOK_SECRET`` is what *enforces* signature validation
   on inbound webhook requests. Without it, every well-formed payload
   is accepted. See :ref:`response-codes` for the gate contract.

Step 3: Mount the URLs
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # urls.py
   from django.urls import include, path

   urlpatterns = [
       # ... your other URLs ...
       path("cloudflare-images/", include("django_cloudflareimages_toolkit.urls")),
   ]

This exposes the webhook at ``https://yourdomain.com/cloudflare-images/api/webhook/``
along with the rest of the toolkit's REST endpoints. The view is
CSRF-exempt by default, so you do **not** need to add it to
``CSRF_EXEMPT_PATHS`` or wrap it.

Step 4: React to status changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The bundled ``WebhookView`` updates the ``CloudflareImage`` row's
``status`` field whenever Cloudflare reports a transition. To react to
those changes in your own code, hook Django's ``post_save`` signal on
``CloudflareImage`` and branch on the new status:

.. code-block:: python

   # apps.py
   from django.apps import AppConfig

   class MyAppConfig(AppConfig):
       name = "myapp"

       def ready(self):
           from django.db.models.signals import post_save
           from django_cloudflareimages_toolkit.models import CloudflareImage
           from . import handlers
           post_save.connect(handlers.on_image_status_change, sender=CloudflareImage)

   # handlers.py
   def on_image_status_change(sender, instance, created, **kwargs):
       if instance.status == "uploaded":
           # Image is live — generate thumbnails, send notifications, etc.
           notify_owner(instance)
       elif instance.status == "failed":
           # Cloudflare rejected the upload — reset the user's UI state
           mark_upload_failed(instance)

If you'd rather process events without going through the database row,
subclass ``WebhookView`` and override ``post``; see
``apps/api/v1/images/cloudflare_views.py`` in
`pacficient-labs/django-cloudflareimages-toolkit
<https://github.com/Pacficient-Labs/django-cloudflareimages-toolkit>`_
for a working example.

Step 5: Configure Cloudflare to deliver
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Follow the `Step-by-Step Webhook Configuration`_ above to register
your public URL (``https://yourdomain.com/cloudflare-images/api/webhook/``)
and the **same secret** you stored in step 2. Cloudflare will start
delivering events on the next direct-creator upload.

Alternative: Using Cloudflare API
----------------------------------

You can also configure webhooks programmatically using the Cloudflare API. This involves two steps:

Step 1: Create Webhook Destination
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   curl -X POST "https://api.cloudflare.com/client/v4/accounts/{account_id}/notification_destinations" \
     -H "Authorization: Bearer {api_token}" \
     -H "Content-Type: application/json" \
     --data '{
       "name": "Django Images Webhook",
       "type": "webhook",
       "webhook": {
         "url": "https://yourdomain.com/cloudflare-images/api/webhook/",
         "secret": "your-webhook-secret"
       }
     }'

Step 2: Create Notification Policy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   curl -X POST "https://api.cloudflare.com/client/v4/accounts/{account_id}/alerting/v3/policies" \
     -H "Authorization: Bearer {api_token}" \
     -H "Content-Type: application/json" \
     --data '{
       "name": "Images Upload Notifications",
       "description": "Notifications for Cloudflare Images uploads",
       "enabled": true,
       "alert_type": "images_upload_complete",
       "mechanisms": {
         "webhooks": ["webhook-destination-id-from-step-1"]
       }
     }'

.. note::
   Replace ``webhook-destination-id-from-step-1`` with the ID returned from the first API call.

.. _response-codes:

Response Codes
--------------

``WebhookView.post`` returns the following statuses. Configure your
upstream monitoring on the **4xx** path for caller errors and the
**5xx** path for genuine outages; that split is meaningful here.

.. list-table::
   :widths: 12 88
   :header-rows: 1

   * - Status
     - When
   * - ``200 OK``
     - Payload validated, processed, image found and updated.
   * - ``400 Bad Request``
     - Body wasn't valid JSON, **or** body parsed but failed
       ``WebhookPayloadSerializer`` validation. The caller sent a
       malformed payload.
   * - ``401 Unauthorized``
     - ``WEBHOOK_SECRET`` is configured **and** the request is missing
       an ``X-Signature`` / ``X-Cloudflare-Signature`` header, **or**
       the supplied signature failed HMAC verification.
   * - ``404 Not Found``
     - Payload was valid but referenced a ``cloudflare_id`` not present
       in the local ``CloudflareImage`` table.
   * - ``500 Internal Server Error``
     - Reserved for genuinely unexpected failures inside
       ``cloudflare_service.process_webhook``. A traceback is logged via
       ``logger.exception``.

.. versionchanged:: 1.0.11
   The signature gate is now enforced when ``WEBHOOK_SECRET`` is set
   (was previously bypassed when the header was absent), and malformed
   payloads now return ``400`` instead of being misclassified as ``500``.
   See the v1.0.11 release notes for the underlying bug analysis.

Webhook Payload Examples
-------------------------

Upload Complete
~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "id": "2cdc28f0-017a-49c4-9ed7-87056c83901",
     "uploaded": "2024-01-01T12:00:00.000Z",
     "variants": [
       "https://imagedelivery.net/Vi7wi5KSItxGFsWRG2Us6Q/2cdc28f0-017a-49c4-9ed7-87056c83901/public",
       "https://imagedelivery.net/Vi7wi5KSItxGFsWRG2Us6Q/2cdc28f0-017a-49c4-9ed7-87056c83901/thumbnail"
     ],
     "metadata": {
       "key": "value"
     },
     "requireSignedURLs": true
   }

Upload Failed
~~~~~~~~~~~~~

.. code-block:: json

   {
     "id": "2cdc28f0-017a-49c4-9ed7-87056c83901",
     "error": "Image processing failed",
     "timestamp": "2024-01-01T12:00:00.000Z"
   }

Troubleshooting
---------------

Common Issues
~~~~~~~~~~~~~

1. **Webhook not receiving requests**
   
   - Check that your Django server is accessible from the internet
   - Verify the webhook URL is correct
   - Check firewall settings

2. **Authentication errors**
   
   - Verify your webhook secret matches in both Cloudflare and Django
   - Check that the secret is properly configured

3. **SSL/TLS errors**
   
   - Ensure your webhook URL uses HTTPS
   - Check that your SSL certificate is valid

Testing Webhooks Locally
~~~~~~~~~~~~~~~~~~~~~~~~~

For local development, you can use tools like ngrok to expose your local server:

.. code-block:: bash

   # Install ngrok
   npm install -g ngrok

   # Expose your local Django server
   ngrok http 8000

   # Use the ngrok URL in your webhook configuration
   # Example: https://abc123.ngrok.io/cloudflare-images/api/webhook/

Webhook Logs
~~~~~~~~~~~~

Check your Django logs for webhook activity:

.. code-block:: python

   # In your Django settings.py
   LOGGING = {
       'version': 1,
       'disable_existing_loggers': False,
       'handlers': {
           'file': {
               'level': 'INFO',
               'class': 'logging.FileHandler',
               'filename': 'cloudflare_webhooks.log',
           },
       },
       'loggers': {
           'django_cloudflareimages_toolkit': {
               'handlers': ['file'],
               'level': 'INFO',
               'propagate': True,
           },
       },
   }

Security Considerations
-----------------------

1. **Always use HTTPS** for webhook URLs
2. **Configure webhook secrets** to verify request authenticity
3. **Validate payload structure** before processing
4. **Rate limit** webhook endpoints if necessary
5. **Log webhook activity** for monitoring and debugging

Monitoring Webhook Health
-------------------------

You can monitor webhook health through:

1. **Django Admin**: View webhook logs in the admin interface
2. **Cloudflare Dashboard**: Check webhook delivery status
3. **Application Logs**: Monitor webhook processing in your logs
4. **Custom Metrics**: Track webhook success/failure rates

Next Steps
----------

After configuring webhooks:

1. Test with a sample image upload
2. Monitor the Django admin for automatic status updates
3. Check logs to ensure webhooks are being processed correctly
4. Set up monitoring and alerting for webhook failures

For more information, see the `Cloudflare Images API documentation <https://developers.cloudflare.com/images/cloudflare-images/api-request/>`_.
