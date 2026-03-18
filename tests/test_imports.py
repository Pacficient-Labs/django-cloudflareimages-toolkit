"""
Test basic imports and package structure
"""

import pytest
from django.test import TestCase, override_settings


@pytest.mark.django_db
class TestImports(TestCase):
    """Test that all package imports work correctly"""

    def test_package_imports(self):
        """Test that main package imports work"""
        from django_cloudflareimages_toolkit import __version__

        self.assertIsInstance(__version__, str)

    def test_model_imports(self):
        """Test that model imports work"""
        from django_cloudflareimages_toolkit.models import (
            CloudflareImage,
            ImageUploadLog,
        )

        self.assertTrue(hasattr(CloudflareImage, "cloudflare_id"))
        self.assertTrue(hasattr(ImageUploadLog, "image"))

    def test_service_imports(self):
        """Test that service imports work"""
        from django_cloudflareimages_toolkit.services import cloudflare_service

        self.assertTrue(hasattr(cloudflare_service, "create_direct_upload_url"))

    def test_transformation_imports(self):
        """Test that transformation imports work"""
        from django_cloudflareimages_toolkit.transformations import (
            CloudflareImageTransform,
            CloudflareImageUtils,
            CloudflareImageVariants,
        )

        self.assertTrue(hasattr(CloudflareImageTransform, "width"))
        self.assertTrue(hasattr(CloudflareImageVariants, "thumbnail"))
        self.assertTrue(hasattr(CloudflareImageUtils, "is_cloudflare_image_url"))

    def test_admin_imports(self):
        """Test that admin imports work"""
        from django_cloudflareimages_toolkit.admin import CloudflareImageAdmin

        self.assertTrue(hasattr(CloudflareImageAdmin, "list_display"))

    def test_settings_configuration(self):
        """Test that Django settings are properly configured"""
        from django.conf import settings

        self.assertIn("django_cloudflareimages_toolkit", settings.INSTALLED_APPS)
        self.assertIn("CLOUDFLARE_IMAGES", dir(settings))
        self.assertEqual(settings.CLOUDFLARE_IMAGES["ACCOUNT_ID"], "test-account-id")

    @override_settings(CLOUDFLARE_IMAGES={})
    def test_service_instantiation_without_settings_does_not_raise(self):
        """
        Importing / instantiating the service must not raise even when required
        settings (ACCOUNT_ID, API_TOKEN) are absent.  The ValueError should only
        be raised lazily, when the required settings are actually accessed — either
        via properties directly or when an API method is called.
        """
        from django_cloudflareimages_toolkit.services import CloudflareImagesService

        # Must not raise at construction time
        service = CloudflareImagesService()

        # Accessing required settings properties must raise ValueError
        with self.assertRaises(ValueError):
            _ = service.account_id

        with self.assertRaises(ValueError):
            _ = service.api_token

    def test_settings_are_read_dynamically(self):
        """Settings changes via override_settings must be reflected immediately.

        Reads values under the default test settings first, then overrides them
        via a context manager and asserts the change is visible immediately,
        proving that settings are not cached at import / instantiation time.
        """
        from django_cloudflareimages_toolkit.settings import cloudflare_settings

        # Confirm the default test-settings values are visible first
        self.assertEqual(cloudflare_settings.account_id, "test-account-id")

        # Applying override_settings as a context manager must be reflected at once
        with override_settings(
            CLOUDFLARE_IMAGES={
                "ACCOUNT_ID": "overridden-id",
                "ACCOUNT_HASH": "overridden-hash",
                "API_TOKEN": "overridden-token",
            }
        ):
            self.assertEqual(cloudflare_settings.account_id, "overridden-id")
            self.assertEqual(cloudflare_settings.api_token, "overridden-token")

        # Values must revert once the override is lifted
        self.assertEqual(cloudflare_settings.account_id, "test-account-id")


class TestTransformations(TestCase):
    """Test transformation functionality without Django models"""

    def test_cloudflare_image_transform(self):
        """Test CloudflareImageTransform functionality"""
        from django_cloudflareimages_toolkit.transformations import (
            CloudflareImageTransform,
        )

        base_url = (
            "https://imagedelivery.net/Vi7wi5KSItxGFsWRG2Us6Q/test-image-id/public"
        )
        transform = CloudflareImageTransform(base_url)

        result = transform.width(300).height(200).build()
        # New format uses full parameter names in comma-separated format
        self.assertIn("width=300", result)
        self.assertIn("height=200", result)
        # URL should replace the variant name with the options
        self.assertIn("imagedelivery.net", result)

    def test_cloudflare_image_transform_cdn_cgi(self):
        """Test CloudflareImageTransform with cdn-cgi format for custom domains"""
        from django_cloudflareimages_toolkit.transformations import (
            CloudflareImageTransform,
        )

        # Test with zone parameter for Image Resizing
        transform = CloudflareImageTransform("/images/photo.jpg", zone="example.com")
        result = transform.width(300).build()
        self.assertIn("/cdn-cgi/image/", result)
        self.assertIn("width=300", result)
        self.assertIn("example.com", result)

    def test_cloudflare_image_variants(self):
        """Test CloudflareImageVariants functionality"""
        from django_cloudflareimages_toolkit.transformations import (
            CloudflareImageVariants,
        )

        base_url = (
            "https://imagedelivery.net/Vi7wi5KSItxGFsWRG2Us6Q/test-image-id/public"
        )

        thumbnail = CloudflareImageVariants.thumbnail(base_url, 150)
        # New format uses full parameter names
        self.assertIn("width=150", thumbnail)
        self.assertIn("height=150", thumbnail)

    def test_cloudflare_image_utils(self):
        """Test CloudflareImageUtils functionality"""
        from django_cloudflareimages_toolkit.transformations import CloudflareImageUtils

        cloudflare_url = (
            "https://imagedelivery.net/Vi7wi5KSItxGFsWRG2Us6Q/test-image-id/public"
        )
        non_cloudflare_url = "https://example.com/image.jpg"

        self.assertTrue(CloudflareImageUtils.is_cloudflare_image_url(cloudflare_url))
        self.assertFalse(
            CloudflareImageUtils.is_cloudflare_image_url(non_cloudflare_url)
        )

        image_id = CloudflareImageUtils.extract_image_id(cloudflare_url)
        self.assertEqual(image_id, "test-image-id")


if __name__ == "__main__":
    pytest.main([__file__])
