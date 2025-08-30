"""
Template tags for Cloudflare Images integration.

This module provides Django template tags for easy integration of
Cloudflare Images transformations and utilities in templates.
"""

from django import template

from ..models import CloudflareImage
from ..transformations import (
    CloudflareImageTransform,
    CloudflareImageUtils,
    CloudflareImageVariants,
)

register = template.Library()


@register.simple_tag
def cf_image_transform(image_url: str, **kwargs) -> str:
    """
    Transform a Cloudflare image URL with specified parameters.

    Usage:
        {% cf_image_transform image.public_url width=300 height=200 fit='cover' quality=85 %}
    """
    if not image_url:
        return ""

    transform = CloudflareImageTransform(image_url)

    # Apply transformations based on kwargs
    if "width" in kwargs:
        transform.width(int(kwargs["width"]))

    if "height" in kwargs:
        transform.height(int(kwargs["height"]))

    if "fit" in kwargs:
        transform.fit(kwargs["fit"])

    if "gravity" in kwargs:
        transform.gravity(kwargs["gravity"])

    if "quality" in kwargs:
        transform.quality(int(kwargs["quality"]))

    if "format" in kwargs:
        transform.format(kwargs["format"])

    if "dpr" in kwargs:
        transform.dpr(float(kwargs["dpr"]))

    if "sharpen" in kwargs:
        transform.sharpen(float(kwargs["sharpen"]))

    if "blur" in kwargs:
        transform.blur(int(kwargs["blur"]))

    if "brightness" in kwargs:
        transform.brightness(float(kwargs["brightness"]))

    if "contrast" in kwargs:
        transform.contrast(float(kwargs["contrast"]))

    if "gamma" in kwargs:
        transform.gamma(float(kwargs["gamma"]))

    if "rotate" in kwargs:
        transform.rotate(int(kwargs["rotate"]))

    if "background" in kwargs:
        transform.background(kwargs["background"])

    if "border_width" in kwargs and "border_color" in kwargs:
        transform.border(int(kwargs["border_width"]), kwargs["border_color"])

    if "pad" in kwargs:
        transform.pad(kwargs["pad"])

    return transform.build()


@register.simple_tag
def cf_thumbnail(image_url: str, size: int = 150) -> str:
    """
    Generate a thumbnail URL.

    Usage:
        {% cf_thumbnail image.public_url 200 %}
    """
    if not image_url:
        return ""
    return CloudflareImageVariants.thumbnail(image_url, size)


@register.simple_tag
def cf_avatar(image_url: str, size: int = 100) -> str:
    """
    Generate an avatar URL.

    Usage:
        {% cf_avatar user.profile_image.public_url 80 %}
    """
    if not image_url:
        return ""
    return CloudflareImageVariants.avatar(image_url, size)


@register.simple_tag
def cf_hero_image(image_url: str, width: int = 1200, height: int = 600) -> str:
    """
    Generate a hero image URL.

    Usage:
        {% cf_hero_image banner.public_url 1920 800 %}
    """
    if not image_url:
        return ""
    return CloudflareImageVariants.hero_image(image_url, width, height)


@register.simple_tag
def cf_responsive_image(image_url: str, width: int, quality: int = 85) -> str:
    """
    Generate a responsive image URL.

    Usage:
        {% cf_responsive_image image.public_url 800 %}
    """
    if not image_url:
        return ""
    return CloudflareImageVariants.responsive_image(image_url, width, quality)


@register.simple_tag
def cf_product_image(image_url: str, size: int = 400) -> str:
    """
    Generate a product image URL with white background.

    Usage:
        {% cf_product_image product.image.public_url 500 %}
    """
    if not image_url:
        return ""
    return CloudflareImageVariants.product_image(image_url, size)


@register.simple_tag
def cf_mobile_optimized(image_url: str, width: int = 400) -> str:
    """
    Generate a mobile-optimized image URL.

    Usage:
        {% cf_mobile_optimized image.public_url 320 %}
    """
    if not image_url:
        return ""
    return CloudflareImageVariants.mobile_optimized(image_url, width)


@register.simple_tag
def cf_srcset(image_url: str, widths: str, quality: int = 85) -> str:
    """
    Generate srcset attribute for responsive images.

    Usage:
        {% cf_srcset image.public_url "320,640,1024,1920" %}
    """
    if not image_url or not widths:
        return ""

    width_list = [int(w.strip()) for w in widths.split(",")]
    return CloudflareImageUtils.get_srcset(image_url, width_list, quality)


@register.simple_tag
def cf_sizes(breakpoints: str) -> str:
    """
    Generate sizes attribute for responsive images.

    Usage:
        {% cf_sizes "max-width: 768px:100vw,max-width: 1024px:50vw,default:800" %}
    """
    if not breakpoints:
        return ""

    breakpoint_dict = {}
    for bp in breakpoints.split(","):
        if ":" in bp:
            condition, width = bp.split(":", 1)
            breakpoint_dict[condition.strip()] = int(
                width.strip().replace("px", "").replace("vw", "")
            )

    return CloudflareImageUtils.get_sizes_attribute(breakpoint_dict)


@register.inclusion_tag("cloudflare_images/responsive_image.html")
def cf_responsive_img(
    image_url: str,
    alt: str = "",
    css_class: str = "",
    widths: str = "320,640,1024",
    quality: int = 85,
    sizes: str = "100vw",
) -> dict:
    """
    Render a complete responsive image element.

    Usage:
        {% cf_responsive_img image.public_url "Alt text" "img-responsive" "320,640,1024" %}
    """
    context = {
        "image_url": image_url,
        "alt": alt,
        "css_class": css_class,
        "quality": quality,
        "sizes": sizes,
    }

    if image_url and widths:
        width_list = [int(w.strip()) for w in widths.split(",")]
        context["srcset"] = CloudflareImageUtils.get_srcset(
            image_url, width_list, quality
        )
        context["src"] = CloudflareImageVariants.responsive_image(
            image_url, width_list[0], quality
        )

    return context


@register.inclusion_tag("cloudflare_images/picture_element.html")
def cf_picture(
    image_url: str,
    alt: str = "",
    css_class: str = "",
    mobile_width: int = 400,
    tablet_width: int = 768,
    desktop_width: int = 1200,
) -> dict:
    """
    Render a picture element with different sources for different screen sizes.

    Usage:
        {% cf_picture image.public_url "Alt text" "responsive-img" 320 768 1200 %}
    """
    context = {"image_url": image_url, "alt": alt, "css_class": css_class}

    if image_url:
        context.update(
            {
                "mobile_src": CloudflareImageVariants.mobile_optimized(
                    image_url, mobile_width
                ),
                "tablet_src": CloudflareImageVariants.responsive_image(
                    image_url, tablet_width
                ),
                "desktop_src": CloudflareImageVariants.responsive_image(
                    image_url, desktop_width
                ),
                "fallback_src": CloudflareImageVariants.responsive_image(
                    image_url, desktop_width
                ),
            }
        )

    return context


@register.filter
def cf_is_cloudflare_url(url: str) -> bool:
    """
    Check if URL is a Cloudflare Images URL.

    Usage:
        {% if image_url|cf_is_cloudflare_url %}
    """
    if not url:
        return False
    return CloudflareImageUtils.is_cloudflare_image_url(url)


@register.filter
def cf_extract_id(url: str) -> str:
    """
    Extract image ID from Cloudflare Images URL.

    Usage:
        {{ image_url|cf_extract_id }}
    """
    if not url:
        return ""
    return CloudflareImageUtils.extract_image_id(url) or ""


@register.filter
def cf_validate_url(url: str) -> bool:
    """
    Validate Cloudflare Images URL format.

    Usage:
        {% if image_url|cf_validate_url %}
    """
    if not url:
        return False
    return CloudflareImageUtils.validate_image_url(url)


@register.simple_tag
def cf_image_info(image_id: str | CloudflareImage) -> CloudflareImage | None:
    """
    Get CloudflareImage instance by ID or return the instance if already provided.

    Usage:
        {% cf_image_info image_id as image_info %}
        {% if image_info.is_uploaded %}
    """
    if isinstance(image_id, CloudflareImage):
        return image_id

    if isinstance(image_id, str):
        try:
            return CloudflareImage.objects.get(cloudflare_id=image_id)
        except CloudflareImage.DoesNotExist:
            return None

    return None


@register.inclusion_tag("cloudflare_images/upload_form.html")
def cf_upload_form(
    form_id: str = "cf-upload-form",
    css_class: str = "cf-upload-form",
    button_text: str = "Upload Image",
    api_endpoint: str = "/api/cloudflare-images/upload-url/",
) -> dict:
    """
    Render an image upload form with JavaScript integration.

    Usage:
        {% cf_upload_form "my-upload-form" "custom-class" "Choose Image" %}
    """
    return {
        "form_id": form_id,
        "css_class": css_class,
        "button_text": button_text,
        "api_endpoint": api_endpoint,
    }


@register.simple_tag(takes_context=True)
def cf_upload_url(context, **kwargs) -> str:
    """
    Generate a direct upload URL (requires authentication).

    Usage:
        {% cf_upload_url metadata='{"type":"avatar"}' as upload_info %}
    """
    request = context.get("request")
    if not request or not request.user.is_authenticated:
        return ""

    # This would typically make an API call to create the upload URL
    # For template usage, this is more of a placeholder
    # Real implementation would require AJAX or form submission
    return ""


@register.inclusion_tag("cloudflare_images/image_gallery.html")
def cf_image_gallery(images, columns: int = 3, thumbnail_size: int = 300) -> dict:
    """
    Render an image gallery with Cloudflare Images.

    Usage:
        {% cf_image_gallery user_images 4 250 %}
    """
    return {"images": images, "columns": columns, "thumbnail_size": thumbnail_size}
