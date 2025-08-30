"""
Django form widgets for Cloudflare Images integration.

This module provides custom form widgets for handling image uploads
with Cloudflare Images, including JavaScript-based upload functionality.
"""

import json
from typing import Any

from django import forms
from django.forms.renderers import get_default_renderer
from django.utils.safestring import SafeText, mark_safe


class CloudflareImageWidget(forms.TextInput):
    """
    A widget for handling Cloudflare image uploads.

    This widget provides a file input interface that handles direct uploads
    to Cloudflare Images and stores the resulting image ID in the form field.
    """

    template_name = (
        "django_cloudflareimages_toolkit/widgets/cloudflare_image_widget.html"
    )

    def __init__(
        self,
        variants: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        require_signed_urls: bool = False,
        max_file_size: int | None = None,
        allowed_formats: list[str] | None = None,
        attrs: dict[str, Any] | None = None,
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
        self.allowed_formats = allowed_formats or ["jpeg", "png", "gif", "webp"]

        default_attrs = {"type": "hidden", "class": "cloudflare-image-field"}
        if attrs:
            default_attrs.update(attrs)

        super().__init__(attrs=default_attrs)

    def format_value(self, value):
        """Format the field value for display."""
        if value is None:
            return ""
        return str(value)

    def render(
        self, name: str, value: Any, attrs: dict[str, Any] | None = None, renderer=None
    ) -> SafeText:
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
        context["widget"].update(
            {
                "variants": self.variants,
                "metadata": self.metadata,
                "require_signed_urls": self.require_signed_urls,
                "max_file_size": self.max_file_size,
                "allowed_formats": self.allowed_formats,
                "config_json": mark_safe(
                    json.dumps(
                        {
                            "variants": self.variants,
                            "metadata": self.metadata,
                            "require_signed_urls": self.require_signed_urls,
                            "max_file_size": self.max_file_size,
                            "allowed_formats": self.allowed_formats,
                        }
                    )
                ),
            }
        )

        # Fallback HTML if template is not found
        try:
            return renderer.render(self.template_name, context)
        except Exception:
            return self._render_fallback(name, value, attrs)

    def _render_fallback(
        self, name: str, value: Any, attrs: dict[str, Any] | None = None
    ) -> SafeText:
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
        field_id = final_attrs.get("id", f"id_{name}")
        upload_id = f"{field_id}_upload"
        preview_id = f"{field_id}_preview"
        progress_id = f"{field_id}_progress"

        # Build the HTML
        html_parts = [
            # Hidden input for storing the image ID
            f'<input type="hidden" name="{name}" id="{field_id}" value="{self.format_value(value)}" />',
            # File input for selecting images
            '<div class="cloudflare-image-upload-container">',
            f'  <input type="file" id="{upload_id}" accept="image/*" class="cloudflare-image-upload" />',
            f'  <div id="{preview_id}" class="cloudflare-image-preview"></div>',
            f'  <div id="{progress_id}" class="cloudflare-image-progress" style="display: none;">',
            '    <div class="progress-bar"></div>',
            '    <span class="progress-text">Uploading...</span>',
            "  </div>",
            "</div>",
            # JavaScript for handling uploads
            "<script>",
            "(function() {",
            f"  const config = {json.dumps({'variants': self.variants, 'metadata': self.metadata, 'require_signed_urls': self.require_signed_urls, 'max_file_size': self.max_file_size, 'allowed_formats': self.allowed_formats})};",
            f'  const fieldId = "{field_id}";',
            f'  const uploadId = "{upload_id}";',
            f'  const previewId = "{preview_id}";',
            f'  const progressId = "{progress_id}";',
            "  ",
            "  // Initialize the upload handler when DOM is ready",
            '  if (document.readyState === "loading") {',
            '    document.addEventListener("DOMContentLoaded", initUploadHandler);',
            "  } else {",
            "    initUploadHandler();",
            "  }",
            "  ",
            "  function initUploadHandler() {",
            "    const uploadInput = document.getElementById(uploadId);",
            "    const hiddenInput = document.getElementById(fieldId);",
            "    const previewDiv = document.getElementById(previewId);",
            "    const progressDiv = document.getElementById(progressId);",
            "    ",
            "    if (!uploadInput) return;",
            "    ",
            '    uploadInput.addEventListener("change", handleFileSelect);',
            "    ",
            "    // Show current image if value exists",
            "    if (hiddenInput.value) {",
            "      showImagePreview(hiddenInput.value);",
            "    }",
            "  }",
            "  ",
            "  function handleFileSelect(event) {",
            "    const file = event.target.files[0];",
            "    if (!file) return;",
            "    ",
            "    // Validate file",
            "    if (!validateFile(file)) return;",
            "    ",
            "    // Start upload",
            "    uploadFile(file);",
            "  }",
            "  ",
            "  function validateFile(file) {",
            "    const maxSize = config.max_file_size;",
            "    const allowedFormats = config.allowed_formats;",
            "    ",
            "    if (maxSize && file.size > maxSize) {",
            '      alert("File size exceeds maximum allowed size");',
            "      return false;",
            "    }",
            "    ",
            '    const fileType = file.type.split("/")[1];',
            "    if (allowedFormats.length && !allowedFormats.includes(fileType)) {",
            '      alert("File format not allowed");',
            "      return false;",
            "    }",
            "    ",
            "    return true;",
            "  }",
            "  ",
            "  async function uploadFile(file) {",
            "    const progressDiv = document.getElementById(progressId);",
            "    const previewDiv = document.getElementById(previewId);",
            "    const hiddenInput = document.getElementById(fieldId);",
            "    ",
            "    try {",
            "      // Show progress",
            '      progressDiv.style.display = "block";',
            '      previewDiv.innerHTML = "";',
            "      ",
            "      // Get upload URL from Django backend",
            '      const uploadUrlResponse = await fetch("/cloudflare-images/get-upload-url/", {',
            '        method: "POST",',
            "        headers: {",
            '          "Content-Type": "application/json",',
            '          "X-CSRFToken": getCsrfToken()',
            "        },",
            "        body: JSON.stringify({",
            "          metadata: config.metadata,",
            "          require_signed_urls: config.require_signed_urls",
            "        })",
            "      });",
            "      ",
            "      if (!uploadUrlResponse.ok) {",
            '        throw new Error("Failed to get upload URL");',
            "      }",
            "      ",
            "      const uploadData = await uploadUrlResponse.json();",
            "      ",
            "      // Upload file to Cloudflare",
            "      const formData = new FormData();",
            '      formData.append("file", file);',
            "      ",
            "      const uploadResponse = await fetch(uploadData.uploadURL, {",
            '        method: "POST",',
            "        body: formData",
            "      });",
            "      ",
            "      if (!uploadResponse.ok) {",
            '        throw new Error("Upload failed");',
            "      }",
            "      ",
            "      const result = await uploadResponse.json();",
            "      ",
            "      // Update hidden input with image ID",
            "      hiddenInput.value = result.result.id;",
            "      ",
            "      // Show preview",
            "      showImagePreview(result.result.id);",
            "      ",
            "      // Hide progress",
            '      progressDiv.style.display = "none";',
            "      ",
            "    } catch (error) {",
            '      console.error("Upload error:", error);',
            '      alert("Upload failed: " + error.message);',
            '      progressDiv.style.display = "none";',
            "    }",
            "  }",
            "  ",
            "  function showImagePreview(imageId) {",
            "    const previewDiv = document.getElementById(previewId);",
            "    if (!imageId) return;",
            "    ",
            "    // Create preview image (you may need to adjust the URL format)",
            '    const img = document.createElement("img");',
            '    img.src = "/cloudflare-images/image/" + imageId + "/thumbnail/";',
            '    img.style.maxWidth = "200px";',
            '    img.style.maxHeight = "200px";',
            '    img.alt = "Image preview";',
            "    ",
            '    previewDiv.innerHTML = "";',
            "    previewDiv.appendChild(img);",
            "  }",
            "  ",
            "  function getCsrfToken() {",
            '    const cookies = document.cookie.split(";");',
            "    for (let cookie of cookies) {",
            '      const [name, value] = cookie.trim().split("=");',
            '      if (name === "csrftoken") {',
            "        return value;",
            "      }",
            "    }",
            '    return "";',
            "  }",
            "})();",
            "</script>",
            # Basic CSS for styling
            "<style>",
            ".cloudflare-image-upload-container {",
            "  border: 2px dashed #ccc;",
            "  border-radius: 4px;",
            "  padding: 20px;",
            "  text-align: center;",
            "  margin: 10px 0;",
            "}",
            ".cloudflare-image-preview img {",
            "  border-radius: 4px;",
            "  box-shadow: 0 2px 4px rgba(0,0,0,0.1);",
            "}",
            ".cloudflare-image-progress {",
            "  margin-top: 10px;",
            "}",
            ".progress-bar {",
            "  width: 100%;",
            "  height: 4px;",
            "  background: #f0f0f0;",
            "  border-radius: 2px;",
            "  overflow: hidden;",
            "}",
            ".progress-bar::after {",
            '  content: "";',
            "  display: block;",
            "  width: 100%;",
            "  height: 100%;",
            "  background: #007cba;",
            "  animation: progress 2s infinite;",
            "}",
            "@keyframes progress {",
            "  0% { transform: translateX(-100%); }",
            "  100% { transform: translateX(100%); }",
            "}",
            "</style>",
        ]

        return mark_safe("".join(html_parts))

    class Media:
        """Define media files for the widget."""

        css = {
            "all": ("django_cloudflareimages_toolkit/css/cloudflare_image_widget.css",)
        }
        js = ("django_cloudflareimages_toolkit/js/cloudflare_image_widget.js",)
