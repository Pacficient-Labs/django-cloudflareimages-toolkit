"""
Django form widgets for Cloudflare Images integration.

This module provides custom form widgets for handling image uploads
with Cloudflare Images, including JavaScript-based upload functionality.
"""

import json
from typing import Any, Dict, List, Optional

from django import forms
from django.forms.renderers import get_default_renderer
from django.utils.safestring import SafeText, mark_safe


class CloudflareImageWidget(forms.TextInput):
    """
    A widget for handling Cloudflare image uploads.

    This widget provides a file input interface that handles direct uploads
    to Cloudflare Images and stores the resulting image ID in the form field.
    """

    template_name = 'django_cloudflareimages_toolkit/widgets/cloudflare_image_widget.html'

    def __init__(
        self,
        variants: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        require_signed_urls: bool = False,
        max_file_size: Optional[int] = None,
        allowed_formats: Optional[List[str]] = None,
        attrs: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the widget.

        Args:
            variants: List of image variants to create
            metadata: Default metadata for uploads
            require_signed_urls: Whether to require signed URLs
            max_file_size: Maximum file size in bytes
            allowed_formats: List of allowed image formats
            attrs: Additional HTML attributes
        """
        self.variants = variants or []
        self.metadata = metadata or {}
        self.require_signed_urls = require_signed_urls
        self.max_file_size = max_file_size
        self.allowed_formats = allowed_formats or [
            'jpeg', 'png', 'gif', 'webp']

        default_attrs = {
            'type': 'hidden',
            'class': 'cloudflare-image-field'
        }
        if attrs:
            default_attrs.update(attrs)

        super().__init__(attrs=default_attrs)

    def format_value(self, value):
        """Format the field value for display."""
        if value is None:
            return ''
        return str(value)

    def render(self, name: str, value: Any, attrs: Optional[Dict[str, Any]] = None, renderer=None) -> SafeText:
        """
        Render the widget HTML.

        Args:
            name: Field name
            value: Current field value
            attrs: HTML attributes
            renderer: Template renderer

        Returns:
            Rendered HTML string
        """
        if renderer is None:
            renderer = get_default_renderer()

        context = self.get_context(name, value, attrs)
        context['widget'].update({
            'variants': self.variants,
            'metadata': self.metadata,
            'require_signed_urls': self.require_signed_urls,
            'max_file_size': self.max_file_size,
            'allowed_formats': self.allowed_formats,
            'config_json': mark_safe(json.dumps({
                'variants': self.variants,
                'metadata': self.metadata,
                'require_signed_urls': self.require_signed_urls,
                'max_file_size': self.max_file_size,
                'allowed_formats': self.allowed_formats,
            }))
        })

        # Fallback HTML if template is not found
        try:
            return renderer.render(self.template_name, context)
        except Exception:
            return self._render_fallback(name, value, attrs)

    def _render_fallback(self, name: str, value: Any, attrs: Optional[Dict[str, Any]] = None) -> SafeText:
        """
        Render fallback HTML when template is not available.

        Args:
            name: Field name
            value: Current field value
            attrs: HTML attributes

        Returns:
            Fallback HTML string
        """
        if attrs is None:
            attrs = {}

        # Merge widget attrs
        final_attrs = self.build_attrs(attrs)

        # Create unique IDs for elements
        field_id = final_attrs.get('id', f'id_{name}')
        upload_id = f'{field_id}_upload'
        preview_id = f'{field_id}_preview'
        progress_id = f'{field_id}_progress'

        # Build the HTML
        html_parts = [
            # Hidden input for storing the image ID
            f'<input type="hidden" name="{name}" id="{field_id}" value="{self.format_value(value)}" />',

            # File input for selecting images
            f'<div class="cloudflare-image-upload-container">',
            f'  <input type="file" id="{upload_id}" accept="image/*" class="cloudflare-image-upload" />',
            f'  <div id="{preview_id}" class="cloudflare-image-preview"></div>',
            f'  <div id="{progress_id}" class="cloudflare-image-progress" style="display: none;">',
            f'    <div class="progress-bar"></div>',
            f'    <span class="progress-text">Uploading...</span>',
            f'  </div>',
            f'</div>',

            # JavaScript for handling uploads
            f'<script>',
            f'(function() {{',
            f'  const config = {json.dumps({
                "variants": self.variants,
                "metadata": self.metadata,
                "require_signed_urls": self.require_signed_urls,
                "max_file_size": self.max_file_size,
                "allowed_formats": self.allowed_formats,
            })};',
            f'  const fieldId = "{field_id}";',
            f'  const uploadId = "{upload_id}";',
            f'  const previewId = "{preview_id}";',
            f'  const progressId = "{progress_id}";',
            f'  ',
            f'  // Initialize the upload handler when DOM is ready',
            f'  if (document.readyState === "loading") {{',
            f'    document.addEventListener("DOMContentLoaded", initUploadHandler);',
            f'  }} else {{',
            f'    initUploadHandler();',
            f'  }}',
            f'  ',
            f'  function initUploadHandler() {{',
            f'    const uploadInput = document.getElementById(uploadId);',
            f'    const hiddenInput = document.getElementById(fieldId);',
            f'    const previewDiv = document.getElementById(previewId);',
            f'    const progressDiv = document.getElementById(progressId);',
            f'    ',
            f'    if (!uploadInput) return;',
            f'    ',
            f'    uploadInput.addEventListener("change", handleFileSelect);',
            f'    ',
            f'    // Show current image if value exists',
            f'    if (hiddenInput.value) {{',
            f'      showImagePreview(hiddenInput.value);',
            f'    }}',
            f'  }}',
            f'  ',
            f'  function handleFileSelect(event) {{',
            f'    const file = event.target.files[0];',
            f'    if (!file) return;',
            f'    ',
            f'    // Validate file',
            f'    if (!validateFile(file)) return;',
            f'    ',
            f'    // Start upload',
            f'    uploadFile(file);',
            f'  }}',
            f'  ',
            f'  function validateFile(file) {{',
            f'    const maxSize = config.max_file_size;',
            f'    const allowedFormats = config.allowed_formats;',
            f'    ',
            f'    if (maxSize && file.size > maxSize) {{',
            f'      alert("File size exceeds maximum allowed size");',
            f'      return false;',
            f'    }}',
            f'    ',
            f'    const fileType = file.type.split("/")[1];',
            f'    if (allowedFormats.length && !allowedFormats.includes(fileType)) {{',
            f'      alert("File format not allowed");',
            f'      return false;',
            f'    }}',
            f'    ',
            f'    return true;',
            f'  }}',
            f'  ',
            f'  async function uploadFile(file) {{',
            f'    const progressDiv = document.getElementById(progressId);',
            f'    const previewDiv = document.getElementById(previewId);',
            f'    const hiddenInput = document.getElementById(fieldId);',
            f'    ',
            f'    try {{',
            f'      // Show progress',
            f'      progressDiv.style.display = "block";',
            f'      previewDiv.innerHTML = "";',
            f'      ',
            f'      // Get upload URL from Django backend',
            f'      const uploadUrlResponse = await fetch("/cloudflare-images/get-upload-url/", {{',
            f'        method: "POST",',
            f'        headers: {{',
            f'          "Content-Type": "application/json",',
            f'          "X-CSRFToken": getCsrfToken()',
            f'        }},',
            f'        body: JSON.stringify({{',
            f'          metadata: config.metadata,',
            f'          require_signed_urls: config.require_signed_urls',
            f'        }})',
            f'      }});',
            f'      ',
            f'      if (!uploadUrlResponse.ok) {{',
            f'        throw new Error("Failed to get upload URL");',
            f'      }}',
            f'      ',
            f'      const uploadData = await uploadUrlResponse.json();',
            f'      ',
            f'      // Upload file to Cloudflare',
            f'      const formData = new FormData();',
            f'      formData.append("file", file);',
            f'      ',
            f'      const uploadResponse = await fetch(uploadData.uploadURL, {{',
            f'        method: "POST",',
            f'        body: formData',
            f'      }});',
            f'      ',
            f'      if (!uploadResponse.ok) {{',
            f'        throw new Error("Upload failed");',
            f'      }}',
            f'      ',
            f'      const result = await uploadResponse.json();',
            f'      ',
            f'      // Update hidden input with image ID',
            f'      hiddenInput.value = result.result.id;',
            f'      ',
            f'      // Show preview',
            f'      showImagePreview(result.result.id);',
            f'      ',
            f'      // Hide progress',
            f'      progressDiv.style.display = "none";',
            f'      ',
            f'    }} catch (error) {{',
            f'      console.error("Upload error:", error);',
            f'      alert("Upload failed: " + error.message);',
            f'      progressDiv.style.display = "none";',
            f'    }}',
            f'  }}',
            f'  ',
            f'  function showImagePreview(imageId) {{',
            f'    const previewDiv = document.getElementById(previewId);',
            f'    if (!imageId) return;',
            f'    ',
            f'    // Create preview image (you may need to adjust the URL format)',
            f'    const img = document.createElement("img");',
            f'    img.src = "/cloudflare-images/image/" + imageId + "/thumbnail/";',
            f'    img.style.maxWidth = "200px";',
            f'    img.style.maxHeight = "200px";',
            f'    img.alt = "Image preview";',
            f'    ',
            f'    previewDiv.innerHTML = "";',
            f'    previewDiv.appendChild(img);',
            f'  }}',
            f'  ',
            f'  function getCsrfToken() {{',
            f'    const cookies = document.cookie.split(";");',
            f'    for (let cookie of cookies) {{',
            f'      const [name, value] = cookie.trim().split("=");',
            f'      if (name === "csrftoken") {{',
            f'        return value;',
            f'      }}',
            f'    }}',
            f'    return "";',
            f'  }}',
            f'}})();',
            f'</script>',

            # Basic CSS for styling
            f'<style>',
            f'.cloudflare-image-upload-container {{',
            f'  border: 2px dashed #ccc;',
            f'  border-radius: 4px;',
            f'  padding: 20px;',
            f'  text-align: center;',
            f'  margin: 10px 0;',
            f'}}',
            f'.cloudflare-image-preview img {{',
            f'  border-radius: 4px;',
            f'  box-shadow: 0 2px 4px rgba(0,0,0,0.1);',
            f'}}',
            f'.cloudflare-image-progress {{',
            f'  margin-top: 10px;',
            f'}}',
            f'.progress-bar {{',
            f'  width: 100%;',
            f'  height: 4px;',
            f'  background: #f0f0f0;',
            f'  border-radius: 2px;',
            f'  overflow: hidden;',
            f'}}',
            f'.progress-bar::after {{',
            f'  content: "";',
            f'  display: block;',
            f'  width: 100%;',
            f'  height: 100%;',
            f'  background: #007cba;',
            f'  animation: progress 2s infinite;',
            f'}}',
            f'@keyframes progress {{',
            f'  0% {{ transform: translateX(-100%); }}',
            f'  100% {{ transform: translateX(100%); }}',
            f'}}',
            f'</style>'
        ]

        return mark_safe(''.join(html_parts))

    class Media:
        """Define media files for the widget."""
        css = {
            'all': ('django_cloudflareimages_toolkit/css/cloudflare_image_widget.css',)
        }
        js = ('django_cloudflareimages_toolkit/js/cloudflare_image_widget.js',)
