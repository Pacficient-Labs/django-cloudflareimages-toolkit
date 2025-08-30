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

For programmatic image uploads, use the ``CloudflareImagesService``:

.. code-block:: python

   from django_cloudflareimages_toolkit.services import CloudflareImagesService
   
   # Initialize the service
   service = CloudflareImagesService()
   
   # Generate a direct upload URL
   upload_data = service.get_direct_upload_url()
   print(f"Upload URL: {upload_data['uploadURL']}")
   print(f"Image ID: {upload_data['id']}")

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

.. code-block:: python

   import json
   from django.http import JsonResponse
   from django.views.decorators.csrf import csrf_exempt
   from django.contrib.auth.decorators import login_required
   from django_cloudflareimages_toolkit.models import CloudflareImage
   
   @csrf_exempt
   @login_required
   def save_image(request):
       if request.method == 'POST':
           try:
               data = json.loads(request.body)
               
               image = CloudflareImage.objects.create(
                   cloudflare_id=data['cloudflare_id'],
                   filename=data['filename'],
                   uploaded_by=request.user  # If you have this field
               )
               
               return JsonResponse({
                   'success': True,
                   'image_id': image.id,
                   'url': image.get_url()
               })
           except Exception as e:
               return JsonResponse({'error': str(e)}, status=500)
       
       return JsonResponse({'error': 'Method not allowed'}, status=405)

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
