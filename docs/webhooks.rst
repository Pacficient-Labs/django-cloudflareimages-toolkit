Webhook Configuration
====================

This guide explains how to configure webhooks in your Cloudflare dashboard to automatically update image status when uploads complete.

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

1. Webhook Secret (Recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Add a webhook secret to your Django settings for security:

.. code-block:: python

   # settings.py
   CLOUDFLARE_IMAGES = {
       'ACCOUNT_ID': 'your-cloudflare-account-id',
       'API_TOKEN': 'your-cloudflare-api-token',
       'WEBHOOK_SECRET': 'your-secure-webhook-secret-key',  # Add this
       # ... other settings
   }

2. URL Configuration
~~~~~~~~~~~~~~~~~~~~

Ensure your webhook URL is accessible:

.. code-block:: python

   # urls.py
   from django.urls import path, include

   urlpatterns = [
       # ... your other URLs
       path('cloudflare-images/', include('django_cloudflareimages_toolkit.urls')),
   ]

This makes the webhook available at: ``https://yourdomain.com/cloudflare-images/api/webhook/``

3. CSRF Exemption
~~~~~~~~~~~~~~~~~

The webhook view is automatically CSRF-exempt, so no additional configuration is needed.

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
