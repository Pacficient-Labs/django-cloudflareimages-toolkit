"""
Image transformation utilities for Cloudflare Images Toolkit.

This module provides comprehensive utilities for working with Cloudflare Images
transformations, variants, and delivery options.
"""

import re
from typing import Any


class CloudflareImageTransform:
    """
    Builder class for Cloudflare image transformations.

    Supports two URL formats:
    1. Cloudflare Images (imagedelivery.net) with flexible variants
    2. Cloudflare Image Resizing (/cdn-cgi/image/) for images on your domain

    Example usage:
        # For Cloudflare Images (flexible variants)
        transform = CloudflareImageTransform(base_url)
        url = transform.width(300).height(200).quality(85).build()

        # For Image Resizing on custom domain
        transform = CloudflareImageTransform(image_path, zone="example.com")
        url = transform.width(300).build()
    """

    def __init__(self, base_url: str, zone: str | None = None):
        """
        Initialize with base image URL.

        Args:
            base_url: The base image URL or path
            zone: Optional zone/domain for Image Resizing (cdn-cgi format).
                  If not provided, assumes Cloudflare Images (imagedelivery.net).
        """
        self.base_url = base_url.rstrip("/")
        self.zone = zone
        self.transforms: dict[str, Any] = {}
        self._is_imagedelivery = "imagedelivery.net" in base_url

    def width(self, width: int) -> "CloudflareImageTransform":
        """Set image width."""
        if width <= 0 or width > 12000:
            raise ValueError("Width must be between 1 and 12000 pixels")
        self.transforms["width"] = width
        return self

    def height(self, height: int) -> "CloudflareImageTransform":
        """Set image height."""
        if height <= 0 or height > 12000:
            raise ValueError("Height must be between 1 and 12000 pixels")
        self.transforms["height"] = height
        return self

    def fit(self, fit_mode: str) -> "CloudflareImageTransform":
        """Set fit mode: scale-down, contain, cover, crop, pad."""
        valid_modes = ["scale-down", "contain", "cover", "crop", "pad"]
        if fit_mode not in valid_modes:
            raise ValueError(f"Fit mode must be one of: {', '.join(valid_modes)}")
        self.transforms["fit"] = fit_mode
        return self

    def gravity(self, gravity: str) -> "CloudflareImageTransform":
        """Set gravity: auto, side, or coordinates."""
        # Validate gravity format
        if gravity not in ["auto", "left", "right", "top", "bottom", "center"]:
            # Check if it's coordinates (e.g., "0.5x0.5")
            if not re.match(r"^[0-1](\.[0-9]+)?x[0-1](\.[0-9]+)?$", gravity):
                raise ValueError("Invalid gravity format")
        self.transforms["gravity"] = gravity
        return self

    def quality(self, quality: int) -> "CloudflareImageTransform":
        """Set image quality (1-100)."""
        if quality < 1 or quality > 100:
            raise ValueError("Quality must be between 1 and 100")
        self.transforms["quality"] = quality
        return self

    def format(self, format_type: str) -> "CloudflareImageTransform":
        """Set output format: auto, webp, avif, jpeg, json."""
        valid_formats = ["auto", "webp", "avif", "jpeg", "json"]
        if format_type not in valid_formats:
            raise ValueError(f"Format must be one of: {', '.join(valid_formats)}")
        self.transforms["format"] = format_type
        return self

    def dpr(self, device_pixel_ratio: float) -> "CloudflareImageTransform":
        """Set device pixel ratio (1.0-3.0)."""
        if device_pixel_ratio < 1.0 or device_pixel_ratio > 3.0:
            raise ValueError("DPR must be between 1.0 and 3.0")
        self.transforms["dpr"] = device_pixel_ratio
        return self

    def sharpen(self, amount: float) -> "CloudflareImageTransform":
        """Set sharpening amount (0.0-10.0)."""
        if amount < 0.0 or amount > 10.0:
            raise ValueError("Sharpen amount must be between 0.0 and 10.0")
        self.transforms["sharpen"] = amount
        return self

    def blur(self, amount: int) -> "CloudflareImageTransform":
        """Set blur amount (1-250)."""
        if amount < 1 or amount > 250:
            raise ValueError("Blur amount must be between 1 and 250")
        self.transforms["blur"] = amount
        return self

    def brightness(self, amount: float) -> "CloudflareImageTransform":
        """Set brightness (-1.0 to 1.0)."""
        if amount < -1.0 or amount > 1.0:
            raise ValueError("Brightness must be between -1.0 and 1.0")
        self.transforms["brightness"] = amount
        return self

    def contrast(self, amount: float) -> "CloudflareImageTransform":
        """Set contrast (-1.0 to 1.0)."""
        if amount < -1.0 or amount > 1.0:
            raise ValueError("Contrast must be between -1.0 and 1.0")
        self.transforms["contrast"] = amount
        return self

    def gamma(self, amount: float) -> "CloudflareImageTransform":
        """Set gamma (0.1 to 9.9)."""
        if amount < 0.1 or amount > 9.9:
            raise ValueError("Gamma must be between 0.1 and 9.9")
        self.transforms["gamma"] = amount
        return self

    def rotate(self, degrees: int) -> "CloudflareImageTransform":
        """Set rotation in degrees (0, 90, 180, 270)."""
        if degrees not in [0, 90, 180, 270]:
            raise ValueError("Rotation must be 0, 90, 180, or 270 degrees")
        if degrees != 0:
            self.transforms["rotate"] = degrees
        return self

    def trim(
        self, color: str | None = None, tolerance: float | None = None
    ) -> "CloudflareImageTransform":
        """Enable automatic trimming of transparent/solid borders."""
        trim_params = []
        if color:
            # Validate hex color
            if not re.match(r"^#?[0-9a-fA-F]{6}$", color):
                raise ValueError("Color must be a valid hex color (e.g., #ffffff)")
            trim_params.append(color.lstrip("#"))
        if tolerance is not None:
            if tolerance < 0.0 or tolerance > 1.0:
                raise ValueError("Tolerance must be between 0.0 and 1.0")
            trim_params.append(str(tolerance))

        self.transforms["trim"] = ";".join(trim_params) if trim_params else "auto"
        return self

    def background(self, color: str) -> "CloudflareImageTransform":
        """Set background color for transparent images."""
        if not re.match(r"^#?[0-9a-fA-F]{6}$", color):
            raise ValueError("Background color must be a valid hex color")
        self.transforms["background"] = color.lstrip("#")
        return self

    def border(self, width: int, color: str) -> "CloudflareImageTransform":
        """Add border with specified width and color."""
        if width < 1 or width > 100:
            raise ValueError("Border width must be between 1 and 100 pixels")
        if not re.match(r"^#?[0-9a-fA-F]{6}$", color):
            raise ValueError("Border color must be a valid hex color")
        self.transforms["border"] = f"{width};{color.lstrip('#')}"
        return self

    def pad(self, padding: int | str) -> "CloudflareImageTransform":
        """Add padding around the image."""
        if isinstance(padding, int):
            if padding < 0 or padding > 500:
                raise ValueError("Padding must be between 0 and 500 pixels")
            self.transforms["pad"] = padding
        else:
            # Validate padding format (e.g., "10,20,30,40")
            if not re.match(r"^\d+(?:,\d+){0,3}$", padding):
                raise ValueError("Invalid padding format")
            self.transforms["pad"] = padding
        return self

    def crop(
        self, x: int, y: int, width: int, height: int
    ) -> "CloudflareImageTransform":
        """Crop image to specified rectangle."""
        if any(val < 0 for val in [x, y, width, height]):
            raise ValueError("Crop values must be non-negative")
        if width == 0 or height == 0:
            raise ValueError("Crop width and height must be greater than 0")
        self.transforms["crop"] = f"{x};{y};{width};{height}"
        return self

    def _build_options_string(self) -> str:
        """Build comma-separated options string for Cloudflare URLs."""
        if not self.transforms:
            return ""
        return ",".join(f"{key}={value}" for key, value in self.transforms.items())

    def build(self) -> str:
        """
        Build the final transformed URL.

        Returns the appropriate URL format based on the base URL:
        - For imagedelivery.net: Uses flexible variant format
        - For custom domains with zone: Uses /cdn-cgi/image/ format
        - For custom domains without zone: Uses /cdn-cgi/image/ format inline
        """
        if not self.transforms:
            return self.base_url

        options = self._build_options_string()

        if self._is_imagedelivery:
            # Cloudflare Images flexible variant format
            # URL: https://imagedelivery.net/<hash>/<id>/<options>
            # Replace the variant name (last path segment) with options
            parts = self.base_url.rsplit("/", 1)
            if len(parts) == 2:
                return f"{parts[0]}/{options}"
            return f"{self.base_url}/{options}"

        if self.zone:
            # Image Resizing with explicit zone
            # URL: https://<zone>/cdn-cgi/image/<options>/<image-path>
            image_path = self.base_url.lstrip("/")
            return f"https://{self.zone}/cdn-cgi/image/{options}/{image_path}"

        # Image Resizing inline format (assumes base_url is full URL)
        # URL: https://example.com/cdn-cgi/image/<options>/path/to/image.jpg
        if self.base_url.startswith("http"):
            from urllib.parse import urlparse

            parsed = urlparse(self.base_url)
            return f"{parsed.scheme}://{parsed.netloc}/cdn-cgi/image/{options}{parsed.path}"

        # Relative path - return with cdn-cgi prefix
        return f"/cdn-cgi/image/{options}/{self.base_url.lstrip('/')}"

    def __str__(self) -> str:
        """Return the built URL."""
        return self.build()


class CloudflareImageVariants:
    """Predefined image variants for common use cases."""

    @staticmethod
    def thumbnail(base_url: str, size: int = 150) -> str:
        """Create a square thumbnail."""
        return (
            CloudflareImageTransform(base_url)
            .width(size)
            .height(size)
            .fit("cover")
            .quality(85)
            .build()
        )

    @staticmethod
    def avatar(base_url: str, size: int = 100) -> str:
        """Create a circular avatar (requires CSS border-radius)."""
        return (
            CloudflareImageTransform(base_url)
            .width(size)
            .height(size)
            .fit("cover")
            .gravity("auto")
            .quality(90)
            .build()
        )

    @staticmethod
    def hero_image(base_url: str, width: int = 1200, height: int = 600) -> str:
        """Create a hero/banner image."""
        return (
            CloudflareImageTransform(base_url)
            .width(width)
            .height(height)
            .fit("cover")
            .gravity("auto")
            .quality(85)
            .format("auto")
            .build()
        )

    @staticmethod
    def responsive_image(base_url: str, width: int, quality: int = 85) -> str:
        """Create a responsive image maintaining aspect ratio."""
        return (
            CloudflareImageTransform(base_url)
            .width(width)
            .fit("scale-down")
            .quality(quality)
            .format("auto")
            .build()
        )

    @staticmethod
    def product_image(base_url: str, size: int = 400) -> str:
        """Create a product image with white background."""
        return (
            CloudflareImageTransform(base_url)
            .width(size)
            .height(size)
            .fit("pad")
            .background("ffffff")
            .quality(90)
            .build()
        )

    @staticmethod
    def gallery_image(base_url: str, width: int = 800, height: int = 600) -> str:
        """Create a gallery image."""
        return (
            CloudflareImageTransform(base_url)
            .width(width)
            .height(height)
            .fit("contain")
            .quality(85)
            .format("auto")
            .build()
        )

    @staticmethod
    def mobile_optimized(base_url: str, width: int = 400) -> str:
        """Create a mobile-optimized image."""
        return (
            CloudflareImageTransform(base_url)
            .width(width)
            .fit("scale-down")
            .quality(80)
            .format("webp")
            .dpr(2.0)
            .build()
        )


class CloudflareImageUtils:
    """Utility functions for Cloudflare Images."""

    @staticmethod
    def extract_image_id(url: str) -> str | None:
        """Extract image ID from Cloudflare Images URL."""
        # Pattern: https://imagedelivery.net/{account_hash}/{image_id}/{variant}
        pattern = r"https://imagedelivery\.net/[^/]+/([^/]+)(?:/[^/]+)?"
        match = re.search(pattern, url)
        return match.group(1) if match else None

    @staticmethod
    def is_cloudflare_image_url(url: str) -> bool:
        """Check if URL is a Cloudflare Images URL."""
        return "imagedelivery.net" in url

    @staticmethod
    def get_srcset(base_url: str, widths: list[int], quality: int = 85) -> str:
        """Generate srcset attribute for responsive images."""
        srcset_parts = []
        for width in widths:
            transformed_url = (
                CloudflareImageTransform(base_url)
                .width(width)
                .fit("scale-down")
                .quality(quality)
                .format("auto")
                .build()
            )
            srcset_parts.append(f"{transformed_url} {width}w")
        return ", ".join(srcset_parts)

    @staticmethod
    def get_sizes_attribute(breakpoints: dict[str, int]) -> str:
        """Generate sizes attribute for responsive images."""
        sizes_parts = []
        for media_query, width in breakpoints.items():
            if media_query == "default":
                sizes_parts.append(f"{width}px")
            else:
                sizes_parts.append(f"({media_query}) {width}px")
        return ", ".join(sizes_parts)

    @staticmethod
    def validate_image_url(url: str) -> bool:
        """Validate if the URL is a properly formatted Cloudflare Images URL."""
        if not CloudflareImageUtils.is_cloudflare_image_url(url):
            return False

        # Check URL structure
        pattern = r"^https://imagedelivery\.net/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)?(?:\?.*)?$"
        return bool(re.match(pattern, url))
