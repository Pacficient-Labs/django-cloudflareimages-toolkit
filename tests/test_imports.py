"""
Test basic imports and package structure
"""

import pytest
from django.conf import settings
from django.test import TestCase


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
        self.assertTrue(hasattr(CloudflareImage, 'cloudflare_id'))
        self.assertTrue(hasattr(ImageUploadLog, 'image'))

    def test_service_imports(self):
        """Test that service imports work"""
        from django_cloudflareimages_toolkit.services import cloudflare_service
        self.assertTrue(hasattr(cloudflare_service,
                        'create_direct_upload_url'))

    def test_transformation_imports(self):
        """Test that transformation imports work"""
        from django_cloudflareimages_toolkit.transformations import (
            CloudflareImageTransform,
            CloudflareImageUtils,
            CloudflareImageVariants,
        )
        self.assertTrue(hasattr(CloudflareImageTransform, 'width'))
        self.assertTrue(hasattr(CloudflareImageVariants, 'thumbnail'))
        self.assertTrue(hasattr(CloudflareImageUtils,
                        'is_cloudflare_image_url'))

    def test_admin_imports(self):
        """Test that admin imports work"""
        from django_cloudflareimages_toolkit.admin import CloudflareImageAdmin
        self.assertTrue(hasattr(CloudflareImageAdmin, 'list_display'))

    def test_settings_configuration(self):
        """Test that Django settings are properly configured"""
        self.assertIn('django_cloudflareimages_toolkit',
                      settings.INSTALLED_APPS)
        self.assertIn('CLOUDFLARE_IMAGES', dir(settings))
        self.assertEqual(
            settings.CLOUDFLARE_IMAGES['ACCOUNT_ID'], 'test-account-id')


class TestTransformations(TestCase):
    """Test transformation functionality without Django models"""

    def test_cloudflare_image_transform(self):
        """Test CloudflareImageTransform functionality"""
        from django_cloudflareimages_toolkit.transformations import (
            CloudflareImageTransform,
        )

        base_url = "https://imagedelivery.net/Vi7wi5KSItxGFsWRG2Us6Q/test-image-id/public"
        transform = CloudflareImageTransform(base_url)

        result = transform.width(300).height(200).build()
        self.assertIn("w=300", result)
        self.assertIn("h=200", result)

    def test_cloudflare_image_variants(self):
        """Test CloudflareImageVariants functionality"""
        from django_cloudflareimages_toolkit.transformations import (
            CloudflareImageVariants,
        )

        base_url = "https://imagedelivery.net/Vi7wi5KSItxGFsWRG2Us6Q/test-image-id/public"

        thumbnail = CloudflareImageVariants.thumbnail(base_url, 150)
        self.assertIn("w=150", thumbnail)
        self.assertIn("h=150", thumbnail)

    def test_cloudflare_image_utils(self):
        """Test CloudflareImageUtils functionality"""
        from django_cloudflareimages_toolkit.transformations import CloudflareImageUtils

        cloudflare_url = "https://imagedelivery.net/Vi7wi5KSItxGFsWRG2Us6Q/test-image-id/public"
        non_cloudflare_url = "https://example.com/image.jpg"

        self.assertTrue(CloudflareImageUtils.is_cloudflare_image_url(cloudflare_url))
        self.assertFalse(
            CloudflareImageUtils.is_cloudflare_image_url(non_cloudflare_url))

        image_id = CloudflareImageUtils.extract_image_id(cloudflare_url)
        self.assertEqual(image_id, "test-image-id")


if __name__ == '__main__':
    pytest.main([__file__])
