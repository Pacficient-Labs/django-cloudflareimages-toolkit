Usage
=====

This guide covers the various ways to use django-cloudflareimages-toolkit in your Django applications.

Model Field Usage
-----------------

The simplest way to use Cloudflare Images is with the ``CloudflareImageField``:

.. code-block:: python

   from django.db import models
   from django_cloudflareimages_toolkit.fields import CloudflareImageField
   
   class Profile(models.Model):
       name = models.CharField(max_length=100)
       avatar = CloudflareImageField()
   
   class Product(models.Model):
       name = models.CharField(max_length=100)
       description = models.TextField()
       image = CloudflareImageField()

Direct Upload Service
---------------------

For programmatic image uploads, use ``CloudflareImagesService``. The
service exposes two related operations: generating a one-time upload
URL (for handing to a browser or another service) and the full
end-to-end flow of uploading a local file from disk straight to
Cloudflare.

Generating a direct upload URL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from django_cloudflareimages_toolkit.services import cloudflare_service

   # Returns a CloudflareImage row with the upload_url populated and
   # status=PENDING. The same row will move to UPLOADED once Cloudflare
   # finishes processing the upload (you can poll via check_image_status
   # or wire up the WebhookView — see docs/webhooks.rst).
   image = cloudflare_service.create_direct_upload_url(
       user=request.user,
       metadata={"category": "profile", "user_id": str(request.user.pk)},
       require_signed_urls=False,
       expiry_minutes=30,
   )

   print(image.cloudflare_id)   # e.g. "2cdc28f0-017a-49c4-9ed7-..."
   print(image.upload_url)      # one-time URL — POST the file here

The full signature is::

   create_direct_upload_url(
       user=None,
       custom_id=None,
       metadata=None,
       require_signed_urls=None,
       expiry_minutes=None,
       creator=None,
   )

Any argument left as ``None`` falls back to its settings default
(``REQUIRE_SIGNED_URLS``, ``DEFAULT_EXPIRY_MINUTES``, ``DEFAULT_METADATA``,
``DEFAULT_CREATOR``). The resolved metadata and creator are sent to
Cloudflare's ``/images/v2/direct_upload`` call and round-tripped onto the
local ``CloudflareImage`` row.

Tagging uploads with a creator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pass ``creator`` to associate an upload with a Cloudflare "creator" value.
It is persisted on the local row and is queryable:

.. code-block:: python

   image = cloudflare_service.create_direct_upload_url(
       user=request.user,
       creator="user-123",
   )

   # The creator is stored on the model and indexed for filtering.
   CloudflareImage.objects.filter(creator="user-123")

When ``creator`` is omitted, the ``DEFAULT_CREATOR`` setting is used. Pass an
explicit empty string (``creator=""``) — also accepted by the REST endpoint — to
force an untagged upload that bypasses ``DEFAULT_CREATOR``.

Customizing metadata with a factory
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For server-side control over the metadata attached to every upload,
configure a metadata factory. Subclass ``ImageMetadataFactory`` and
override ``get_metadata``:

.. code-block:: python

   from django_cloudflareimages_toolkit import ImageMetadataFactory

   class TenantMetadataFactory(ImageMetadataFactory):
       def get_metadata(self, *, metadata, user=None, **context):
           if user is not None:
               metadata['uploaded_by'] = str(user.pk)
           metadata['source'] = 'web'
           return metadata

The signature you override is::

   def get_metadata(self, *, metadata, user=None, custom_id=None,
                    creator=None, **context) -> dict

Factory instances are callable. Register it via the ``METADATA_FACTORY``
setting (a dotted import path string, a class, an instance, or any callable):

.. code-block:: python

   CLOUDFLARE_IMAGES = {
       # ... other settings
       'METADATA_FACTORY': 'myapp.factories.TenantMetadataFactory',
   }

The factory receives the already-resolved metadata (``DEFAULT_METADATA``
merged with per-request metadata) plus upload context, and returns the
final metadata dict that is sent to Cloudflare and persisted. The merge
precedence, lowest to highest, is::

   DEFAULT_METADATA < per-request metadata < factory output

The factory is trusted server-side code and has the final say — it can
augment or override keys supplied by the client.

Server-side: uploading a local file from disk
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A common pattern is to upload an image stored on the Django server
(generated thumbnail, imported asset, content-management workflow)
straight to Cloudflare without involving a browser. The toolkit drives
this through the same Direct Creator Upload primitive — get an upload
URL from Cloudflare, then ``POST`` the file bytes to it.

.. code-block:: python

   import requests
   from django_cloudflareimages_toolkit.services import cloudflare_service
   from django_cloudflareimages_toolkit.exceptions import CloudflareImagesError


   def upload_local_image(path: str, *, user=None, metadata=None):
       """Upload a file from disk to Cloudflare Images.

       Returns the populated CloudflareImage row.
       """
       # 1. Reserve a one-time upload slot. The returned CloudflareImage
       #    is already persisted with status=PENDING, so a webhook or
       #    a later check_image_status() call has a row to update.
       image = cloudflare_service.create_direct_upload_url(
           user=user,
           metadata=metadata or {},
           expiry_minutes=30,
       )

       # 2. POST the bytes. Cloudflare's Direct Creator endpoint expects
       #    multipart/form-data with the file under the field name "file".
       with open(path, "rb") as fh:
           response = requests.post(
               image.upload_url,
               files={"file": (image.cloudflare_id, fh, "application/octet-stream")},
               timeout=60,
           )

       if not response.ok:
           raise CloudflareImagesError(
               f"Cloudflare upload POST failed: {response.status_code} {response.text[:200]}"
           )

       # 3. Sync the local row with the now-uploaded state. This is
       #    idempotent — the webhook (if configured) will also drive
       #    this transition.
       cloudflare_service.check_image_status(image)
       image.refresh_from_db()
       return image


   # Usage
   image = upload_local_image(
       "/srv/media/incoming/banner.jpg",
       user=request.user,
       metadata={"source": "cms_import"},
   )
   print(image.status)             # "uploaded"
   print(image.public_url)         # delivery URL
   print(image.get_variant_url("thumbnail"))

The same pattern works for ``BytesIO`` and ``InMemoryUploadedFile`` —
swap the ``open(path, "rb")`` line for the file-like object you already
have.

.. note::

   The upload URL is single-use and expires per ``expiry_minutes`` (2–360
   minutes; default 30). If you batch hundreds of uploads, request one
   URL per file rather than reusing — Cloudflare rejects reuse.

For production-grade retry, circuit-breaking, and graceful degradation
around this flow, see :doc:`patterns`.

Bulk uploads
~~~~~~~~~~~~

For batch jobs, push each ``upload_local_image`` call through a task
queue rather than running them inline. A Celery example:

.. code-block:: python

   from celery import shared_task
   from django_cloudflareimages_toolkit.exceptions import CloudflareImagesError

   @shared_task(
       bind=True,
       autoretry_for=(CloudflareImagesError, requests.RequestException),
       retry_backoff=True,
       retry_backoff_max=300,
       retry_jitter=True,
       max_retries=8,
   )
   def upload_local_image_async(self, path: str, *, user_id: int | None = None):
       from django.contrib.auth import get_user_model
       user = get_user_model().objects.get(pk=user_id) if user_id else None
       return upload_local_image(path, user=user).cloudflare_id

This pattern is covered in more detail (with circuit-breaker + cache
fallback) in :doc:`patterns`.

Frontend Integration
--------------------

Use the direct upload URLs for secure client-side uploads:

JavaScript Upload Example
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: html

   <!-- HTML form -->
   <form id="upload-form">
       <input type="file" id="image-input" accept="image/*">
       <button type="submit">Upload Image</button>
       <div id="progress"></div>
   </form>

.. code-block:: javascript

   // JavaScript upload handler
   document.getElementById('upload-form').addEventListener('submit', async (e) => {
       e.preventDefault();
       
       const fileInput = document.getElementById('image-input');
       const file = fileInput.files[0];
       
       if (!file) return;
       
       try {
           // Get upload URL from your Django backend
           const response = await fetch('/api/get-upload-url/');
           const uploadData = await response.json();
           
           // Upload directly to Cloudflare
           const formData = new FormData();
           formData.append('file', file);
           
           const uploadResponse = await fetch(uploadData.uploadURL, {
               method: 'POST',
               body: formData
           });
           
           if (uploadResponse.ok) {
               const result = await uploadResponse.json();
               console.log('Upload successful:', result);
               
               // Save image reference in your Django app
               await fetch('/api/save-image/', {
                   method: 'POST',
                   headers: {
                       'Content-Type': 'application/json',
                       'X-CSRFToken': getCookie('csrftoken')
                   },
                   body: JSON.stringify({
                       cloudflare_id: result.result.id,
                       filename: file.name
                   })
               });
           }
       } catch (error) {
           console.error('Upload failed:', error);
       }
   });

Django Views for Upload
-----------------------

Create views to handle upload URL generation and image saving:

Upload URL Generation
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from django.http import JsonResponse
   from django.views.decorators.csrf import csrf_exempt
   from django.contrib.auth.decorators import login_required
   from django_cloudflareimages_toolkit.services import CloudflareImagesService
   
   @login_required
   def get_upload_url(request):
       try:
           service = CloudflareImagesService()
           upload_data = service.get_direct_upload_url()
           
           return JsonResponse({
               'uploadURL': upload_data['uploadURL'],
               'id': upload_data['id']
           })
       except Exception as e:
           return JsonResponse({'error': str(e)}, status=500)

Image Saving
~~~~~~~~~~~~

When a client reports back the ``cloudflare_id`` it uploaded, use
``CloudflareImage.objects.register_uploaded`` to register it safely. The
manager fetches the image from Cloudflare, confirms it exists and that its
draft state is cleared, then creates (or returns) the local record
populated with status, variants, metadata, and creator.

.. code-block:: python

   import json
   from django.http import JsonResponse
   from django.views.decorators.csrf import csrf_exempt
   from django.contrib.auth.decorators import login_required
   from django_cloudflareimages_toolkit.models import CloudflareImage
   from django_cloudflareimages_toolkit.exceptions import (
       ImageNotFoundError, ImageNotReadyError,
   )

   @csrf_exempt
   @login_required
   def save_image(request):
       if request.method == 'POST':
           data = json.loads(request.body)
           try:
               image = CloudflareImage.objects.register_uploaded(
                   data['cloudflare_id'],
                   user=request.user,
               )
           except ImageNotFoundError:
               return JsonResponse({'error': 'Image not found in Cloudflare'}, status=404)
           except ImageNotReadyError:
               return JsonResponse({'error': 'Upload not completed yet'}, status=409)

           return JsonResponse({
               'success': True,
               'image_id': image.id,
               'url': image.get_url()
           })

       return JsonResponse({'error': 'Method not allowed'}, status=405)

.. warning::

   Do **not** call ``CloudflareImage.objects.get_or_create(cloudflare_id=...)``
   directly with a client-supplied id. The id may not exist, may still be a
   draft, or may belong to another user, and doing so leaves a bare local row
   that does not correspond to a real Cloudflare image.
   ``register_uploaded`` is the recommended path: it validates the id against
   Cloudflare before persisting anything, and raises ``ImageNotFoundError``
   (id does not exist) or ``ImageNotReadyError`` (exists but still a draft)
   without creating a local row on failure. When you set ``creator`` at upload
   time, also pass ``expected_creator=str(request.user.pk)`` so a caller can
   only register their own image — a mismatch raises ``ImageOwnershipError``.

Using in Django Forms
---------------------

Integrate Cloudflare Images with Django forms:

Form Definition
~~~~~~~~~~~~~~~

.. code-block:: python

   from django import forms
   from django_cloudflareimages_toolkit.fields import CloudflareImageField
   
   class ProfileForm(forms.ModelForm):
       class Meta:
           model = Profile
           fields = ['name', 'avatar']
           widgets = {
               'avatar': forms.HiddenInput(),  # Hidden field for image ID
           }
   
   class ProductForm(forms.Form):
       name = forms.CharField(max_length=100)
       description = forms.CharField(widget=forms.Textarea)
       image = forms.CharField(widget=forms.HiddenInput())  # Store Cloudflare ID

Form Template
~~~~~~~~~~~~~

.. code-block:: html

   <!-- templates/profile_form.html -->
   <form method="post" id="profile-form">
       {% csrf_token %}
       {{ form.name }}
       
       <!-- Custom image upload widget -->
       <div class="image-upload">
           <input type="file" id="image-input" accept="image/*">
           <div id="image-preview"></div>
           {{ form.avatar }}  <!-- Hidden field -->
       </div>
       
       <button type="submit">Save Profile</button>
   </form>
   
   <script>
   // Handle image upload and form submission
   document.getElementById('image-input').addEventListener('change', async (e) => {
       const file = e.target.files[0];
       if (!file) return;
       
       // Upload to Cloudflare and update hidden field
       const uploadData = await uploadToCloudflare(file);
       document.getElementById('id_avatar').value = uploadData.id;
       
       // Show preview
       const preview = document.getElementById('image-preview');
       preview.innerHTML = `<img src="${uploadData.url}" style="max-width: 200px;">`;
   });
   </script>

Image Transformations
---------------------

The toolkit provides powerful image transformation capabilities using Cloudflare's
flexible variants and Image Resizing features.

CloudflareImageTransform
~~~~~~~~~~~~~~~~~~~~~~~~

Use ``CloudflareImageTransform`` to build transformation URLs:

.. code-block:: python

   from django_cloudflareimages_toolkit.transformations import CloudflareImageTransform

   # For Cloudflare Images (imagedelivery.net)
   # Transforms are applied as path-based options: width=300,height=200
   transform = CloudflareImageTransform(image.public_url)
   thumbnail_url = (transform
       .width(300)
       .height(300)
       .fit('cover')
       .quality(85)
       .build())
   # Result: https://imagedelivery.net/<hash>/<id>/width=300,height=300,fit=cover,quality=85

   # For Image Resizing on custom domains (cdn-cgi format)
   transform = CloudflareImageTransform("/images/photo.jpg", zone="example.com")
   resized_url = transform.width(800).quality(85).build()
   # Result: https://example.com/cdn-cgi/image/width=800,quality=85/images/photo.jpg

Available Transformations
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   transform = CloudflareImageTransform(base_url)

   # Dimensions
   transform.width(800)          # Width in pixels (1-12000)
   transform.height(600)         # Height in pixels (1-12000)

   # Fit modes
   transform.fit('scale-down')   # Scale down only, never enlarge
   transform.fit('contain')      # Fit within dimensions, preserve aspect ratio
   transform.fit('cover')        # Fill dimensions, crop if needed
   transform.fit('crop')         # Crop to exact dimensions
   transform.fit('pad')          # Pad to dimensions with background

   # Quality and format
   transform.quality(85)         # Quality 1-100
   transform.format('webp')      # Output format: auto, webp, avif, jpeg, json

   # Visual adjustments
   transform.blur(10)            # Blur amount 1-250
   transform.sharpen(2.0)        # Sharpen 0.0-10.0
   transform.brightness(0.1)     # Brightness -1.0 to 1.0
   transform.contrast(0.1)       # Contrast -1.0 to 1.0
   transform.gamma(1.2)          # Gamma 0.1-9.9

   # Cropping and positioning
   transform.gravity('auto')     # auto, left, right, top, bottom, center
   transform.rotate(90)          # Rotation: 0, 90, 180, 270

   # Borders and background
   transform.background('ffffff')  # Background color (hex)
   transform.border(2, 'cccccc')   # Border width and color

   # Device pixel ratio
   transform.dpr(2.0)            # DPR 1.0-3.0 for retina displays

Predefined Variants
~~~~~~~~~~~~~~~~~~~

Use ``CloudflareImageVariants`` for common use cases:

.. code-block:: python

   from django_cloudflareimages_toolkit.transformations import CloudflareImageVariants

   # Square thumbnail
   thumbnail = CloudflareImageVariants.thumbnail(image.public_url, 150)

   # Circular avatar (requires CSS border-radius)
   avatar = CloudflareImageVariants.avatar(image.public_url, 100)

   # Hero/banner image
   hero = CloudflareImageVariants.hero_image(image.public_url, 1920, 800)

   # Responsive image
   responsive = CloudflareImageVariants.responsive_image(image.public_url, 800)

   # Product image with white background
   product = CloudflareImageVariants.product_image(image.public_url, 400)

   # Mobile-optimized WebP
   mobile = CloudflareImageVariants.mobile_optimized(image.public_url, 400)

Responsive Images
~~~~~~~~~~~~~~~~~

Generate srcset for responsive images:

.. code-block:: python

   from django_cloudflareimages_toolkit.transformations import CloudflareImageUtils

   # Generate srcset attribute
   srcset = CloudflareImageUtils.get_srcset(
       image.public_url,
       widths=[320, 640, 1024, 1920],
       quality=85
   )
   # Result: "url 320w, url 640w, url 1024w, url 1920w"

   # Generate sizes attribute
   sizes = CloudflareImageUtils.get_sizes_attribute({
       'max-width: 768px': 100,   # 100vw on mobile
       'max-width: 1024px': 50,   # 50vw on tablet
       'default': 800             # 800px on desktop
   })

Template Usage
--------------

Display images in your Django templates:

Basic Image Display
~~~~~~~~~~~~~~~~~~~

.. code-block:: html

   <!-- Display original image -->
   <img src="{{ profile.avatar.get_url }}" alt="Profile Avatar">
   
   <!-- Display with specific variant -->
   <img src="{{ profile.avatar.get_url:'thumbnail' }}" alt="Avatar Thumbnail">
   
   <!-- Display with fallback -->
   {% if profile.avatar %}
       <img src="{{ profile.avatar.get_url }}" alt="Profile Avatar">
   {% else %}
       <img src="{% static 'images/default-avatar.png' %}" alt="Default Avatar">
   {% endif %}

Advanced Template Usage
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: html

   <!-- Product gallery -->
   <div class="product-gallery">
       {% for product in products %}
           <div class="product-card">
               <img src="{{ product.image.get_url:'thumbnail' }}" 
                    alt="{{ product.name }}"
                    onclick="showLargeImage('{{ product.image.get_url }}')">
               <h3>{{ product.name }}</h3>
               <p>{{ product.description|truncatewords:20 }}</p>
           </div>
       {% endfor %}
   </div>

Image Management
----------------

Programmatically manage images using the service:

List Images
~~~~~~~~~~~

.. code-block:: python

   from django_cloudflareimages_toolkit.services import CloudflareImagesService
   
   service = CloudflareImagesService()
   
   # List all images
   images = service.list_images()
   for image in images['result']['images']:
       print(f"Image ID: {image['id']}")
       print(f"Filename: {image['filename']}")
       print(f"Uploaded: {image['uploaded']}")

Get Image Details
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Get specific image details
   image_id = "your-image-id"
   image_details = service.get_image(image_id)
   
   print(f"Image URL: {image_details['result']['variants'][0]}")
   print(f"Metadata: {image_details['result']['meta']}")

Delete Images
~~~~~~~~~~~~~

.. code-block:: python

   # Delete an image
   image_id = "your-image-id"
   result = service.delete_image(image_id)
   
   if result['success']:
       print("Image deleted successfully")

Webhook Handling
----------------

Handle real-time upload notifications:

Webhook View
~~~~~~~~~~~~

.. code-block:: python

   import json
   import hmac
   import hashlib
   from django.http import HttpResponse
   from django.views.decorators.csrf import csrf_exempt
   from django.conf import settings
   from django_cloudflareimages_toolkit.models import CloudflareImage
   
   @csrf_exempt
   def cloudflare_webhook(request):
       if request.method == 'POST':
           # Verify webhook signature
           signature = request.headers.get('CF-Webhook-Signature')
           if not verify_webhook_signature(request.body, signature):
               return HttpResponse(status=401)
           
           try:
               data = json.loads(request.body)
               
               # Handle upload completion
               if data.get('event') == 'upload.complete':
                   image_id = data['data']['id']
                   
                   # Update image status
                   try:
                       image = CloudflareImage.objects.get(cloudflare_id=image_id)
                       image.is_ready = True
                       image.file_size = data['data'].get('size')
                       image.width = data['data'].get('width')
                       image.height = data['data'].get('height')
                       image.format = data['data'].get('format')
                       image.save()
                   except CloudflareImage.DoesNotExist:
                       # Create new image record if it doesn't exist
                       CloudflareImage.objects.create(
                           cloudflare_id=image_id,
                           filename=data['data'].get('filename', ''),
                           is_ready=True,
                           file_size=data['data'].get('size'),
                           width=data['data'].get('width'),
                           height=data['data'].get('height'),
                           format=data['data'].get('format')
                       )
               
               return HttpResponse(status=200)
           except Exception as e:
               return HttpResponse(status=500)
       
       return HttpResponse(status=405)
   
   def verify_webhook_signature(payload, signature):
       webhook_secret = settings.CLOUDFLARE_IMAGES.get('WEBHOOK_SECRET')
       if not webhook_secret:
           return False
       
       expected_signature = hmac.new(
           webhook_secret.encode(),
           payload,
           hashlib.sha256
       ).hexdigest()
       
       return hmac.compare_digest(signature, expected_signature)

Admin Integration
-----------------

The package provides Django admin integration:

Custom Admin Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from django.contrib import admin
   from django_cloudflareimages_toolkit.admin import CloudflareImageAdmin
   from django_cloudflareimages_toolkit.models import CloudflareImage
   
   # Customize the admin interface
   @admin.register(CloudflareImage)
   class CustomCloudflareImageAdmin(CloudflareImageAdmin):
       list_display = ['filename', 'uploaded_at', 'file_size', 'is_ready', 'image_preview']
       list_filter = ['is_ready', 'format', 'uploaded_at']
       search_fields = ['filename', 'cloudflare_id']
       readonly_fields = ['cloudflare_id', 'uploaded_at', 'file_size', 'width', 'height']
       
       def image_preview(self, obj):
           if obj.is_ready:
               return f'<img src="{obj.get_url("thumbnail")}" style="max-height: 50px;">'
           return "Processing..."
       image_preview.allow_tags = True
       image_preview.short_description = "Preview"

Management Commands
-------------------

Use the provided management commands:

Cleanup Expired Images
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Clean up expired upload URLs
   python manage.py cleanup_expired_images
   
   # Clean up images older than 7 days
   python manage.py cleanup_expired_images --days 7
   
   # Dry run to see what would be deleted
   python manage.py cleanup_expired_images --dry-run

Testing
-------

Test image functionality in your Django tests:

.. code-block:: python

   from django.test import TestCase
   from unittest.mock import patch, MagicMock
   from django_cloudflareimages_toolkit.services import CloudflareImagesService
   from django_cloudflareimages_toolkit.models import CloudflareImage
   
   class CloudflareImagesTestCase(TestCase):
       @patch('django_cloudflareimages_toolkit.services.requests.post')
       def test_get_direct_upload_url(self, mock_post):
           # Mock the API response
           mock_response = MagicMock()
           mock_response.json.return_value = {
               'success': True,
               'result': {
                   'id': 'test-image-id',
                   'uploadURL': 'https://upload.imagedelivery.net/test-url'
               }
           }
           mock_post.return_value = mock_response
           
           service = CloudflareImagesService()
           result = service.get_direct_upload_url()
           
           self.assertEqual(result['id'], 'test-image-id')
           self.assertIn('uploadURL', result)
       
       def test_cloudflare_image_model(self):
           image = CloudflareImage.objects.create(
               cloudflare_id='test-id',
               filename='test.jpg',
               is_ready=True
           )
           
           self.assertEqual(str(image), 'test.jpg')
           self.assertTrue(image.get_url().startswith('https://imagedelivery.net/'))

Best Practices
--------------

1. **Security First**: Always verify webhook signatures and validate uploads
2. **Error Handling**: Implement proper error handling for upload failures
3. **User Feedback**: Provide clear feedback during upload processes
4. **Image Optimization**: Use appropriate variants for different use cases
5. **Cleanup**: Regularly clean up expired upload URLs and unused images
6. **Testing**: Test upload functionality across different browsers and devices
7. **Monitoring**: Monitor upload success rates and performance
8. **Backup Strategy**: Consider backup strategies for critical images
9. **Rate Limiting**: Implement rate limiting for upload endpoints
10. **Progressive Enhancement**: Ensure your app works without JavaScript for uploads

Performance Tips
----------------

1. **Use Variants**: Create and use appropriate image variants instead of resizing originals
2. **Lazy Loading**: Implement lazy loading for image-heavy pages
3. **CDN Benefits**: Leverage Cloudflare's global CDN for fast image delivery
4. **Async Uploads**: Use asynchronous uploads to improve user experience
5. **Batch Operations**: Batch multiple image operations when possible
6. **Caching**: Cache image URLs and metadata appropriately
7. **Compression**: Use appropriate image formats and compression settings
