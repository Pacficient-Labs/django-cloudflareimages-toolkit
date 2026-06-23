---
title: "Template Tags"
description: "Reference for the Django template tags and filters provided by the cloudflare_images tag library."
---

Source file: `django_cloudflareimages_toolkit/templatetags/cloudflare_images.py`

Load the library with:

```html
{% load cloudflare_images %}
```

## Simple tags

```python
def cf_image_transform(image_url: str, **kwargs) -> str: ...
def cf_thumbnail(image_url: str, size: int = 150) -> str: ...
def cf_avatar(image_url: str, size: int = 100) -> str: ...
def cf_hero_image(image_url: str, width: int = 1200, height: int = 600) -> str: ...
def cf_responsive_image(image_url: str, width: int, quality: int = 85) -> str: ...
def cf_product_image(image_url: str, size: int = 400) -> str: ...
def cf_mobile_optimized(image_url: str, width: int = 400) -> str: ...
def cf_srcset(image_url: str, widths: str, quality: int = 85) -> str: ...
def cf_sizes(breakpoints: str) -> str: ...
def cf_image_info(image_id: str | CloudflareImage) -> CloudflareImage | None: ...
def cf_upload_url(context, **kwargs) -> str: ...
```

Example:

```html
<img
  src="{% cf_responsive_image image.public_url 800 %}"
  srcset="{% cf_srcset image.public_url '320,640,1024' %}"
  sizes="{% cf_sizes 'max-width: 768px:100vw,default:800' %}"
  alt="Example"
>
```

## Inclusion tags

```python
def cf_responsive_img(
    image_url: str,
    alt: str = "",
    css_class: str = "",
    widths: str = "320,640,1024",
    quality: int = 85,
    sizes: str = "100vw",
) -> dict: ...

def cf_picture(
    image_url: str,
    alt: str = "",
    css_class: str = "",
    mobile_width: int = 400,
    tablet_width: int = 768,
    desktop_width: int = 1200,
) -> dict: ...

def cf_upload_form(
    form_id: str = "cf-upload-form",
    css_class: str = "cf-upload-form",
    button_text: str = "Upload Image",
    api_endpoint: str | None = None,  # defaults to reverse("cloudflare_images:create-upload-url")
) -> dict: ...

def cf_image_gallery(images, columns: int = 3, thumbnail_size: int = 300) -> dict: ...
```

These tags return context dictionaries intended for templates such as `cloudflare_images/responsive_image.html`, `cloudflare_images/picture_element.html`, `cloudflare_images/upload_form.html`, and `cloudflare_images/image_gallery.html`. If you use them, make sure those templates exist in your project because they are not present in the source tree.

## Filters

```python
def cfimg_status_color(status) -> str: ...
def cf_is_cloudflare_url(url: str) -> bool: ...
def cf_extract_id(url: str) -> str: ...
def cf_validate_url(url: str) -> bool: ...
```

Example:

```html
{% if image.public_url|cf_validate_url %}
  {{ image.public_url|cf_extract_id }}
{% endif %}
```

The tag library is deliberately thin. Most tags delegate directly to `CloudflareImageTransform`, `CloudflareImageVariants`, or `CloudflareImageUtils`, so behavior stays consistent between Python code and templates.
