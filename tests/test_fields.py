"""
Tests for CloudflareImageField and related functionality.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.test import TestCase

from django_cloudflareimages_toolkit.fields import (
    CloudflareImageField,
    CloudflareImageFieldValue,
)
from django_cloudflareimages_toolkit.models import CloudflareImage


class TestModel(models.Model):
    """Test model for CloudflareImageField testing."""
    name = models.CharField(max_length=100)
    image = CloudflareImageField()

    class Meta:
        app_label = 'tests'


class CloudflareImageFieldTest(TestCase):
    """Test cases for CloudflareImageField."""

    def test_field_creation(self):
        """Test that CloudflareImageField can be created with various options."""
        field = CloudflareImageField(
            variants=['thumbnail', 'large'],
            metadata={'category': 'test'},
            require_signed_urls=True,
            max_file_size=1024 * 1024,
            allowed_formats=['jpeg', 'png']
        )

        self.assertEqual(field.variants, ['thumbnail', 'large'])
        self.assertEqual(field.metadata, {'category': 'test'})
        self.assertTrue(field.require_signed_urls)
        self.assertEqual(field.max_file_size, 1024 * 1024)
        self.assertEqual(field.allowed_formats, ['jpeg', 'png'])

    def test_field_defaults(self):
        """Test that CloudflareImageField has correct defaults."""
        field = CloudflareImageField()

        self.assertEqual(field.variants, [])
        self.assertEqual(field.metadata, {})
        self.assertFalse(field.require_signed_urls)
        self.assertIsNone(field.max_file_size)
        self.assertEqual(field.allowed_formats, ['jpeg', 'png', 'gif', 'webp'])

    def test_to_python_with_none(self):
        """Test to_python method with None value."""
        field = CloudflareImageField()
        result = field.to_python(None)
        self.assertIsNone(result)

    def test_to_python_with_empty_string(self):
        """Test to_python method with empty string."""
        field = CloudflareImageField()
        result = field.to_python('')
        self.assertIsNone(result)

    def test_to_python_with_string(self):
        """Test to_python method with string value."""
        field = CloudflareImageField()
        result = field.to_python('test-image-id')

        self.assertIsInstance(result, CloudflareImageFieldValue)
        if result is not None:
            self.assertEqual(result.cloudflare_id, 'test-image-id')
            self.assertEqual(result.field, field)

    def test_to_python_with_field_value(self):
        """Test to_python method with CloudflareImageFieldValue."""
        field = CloudflareImageField()
        field_value = CloudflareImageFieldValue('test-id', field)
        result = field.to_python(field_value)

        self.assertEqual(result, field_value)

    def test_to_python_with_invalid_value(self):
        """Test to_python method with invalid value."""
        field = CloudflareImageField()

        with self.assertRaises(ValidationError):
            field.to_python(123)

    def test_get_prep_value_with_none(self):
        """Test get_prep_value method with None."""
        field = CloudflareImageField()
        result = field.get_prep_value(None)
        self.assertIsNone(result)

    def test_get_prep_value_with_string(self):
        """Test get_prep_value method with string."""
        field = CloudflareImageField()
        result = field.get_prep_value('test-id')
        self.assertEqual(result, 'test-id')

    def test_get_prep_value_with_field_value(self):
        """Test get_prep_value method with CloudflareImageFieldValue."""
        field = CloudflareImageField()
        field_value = CloudflareImageFieldValue('test-id', field)
        result = field.get_prep_value(field_value)
        self.assertEqual(result, 'test-id')

    def test_deconstruct(self):
        """Test field deconstruction for migrations."""
        field = CloudflareImageField(
            variants=['thumbnail'],
            metadata={'test': True},
            require_signed_urls=True,
            max_file_size=1024,
            allowed_formats=['jpeg']
        )

        name, path, args, kwargs = field.deconstruct()

        self.assertEqual(kwargs['variants'], ['thumbnail'])
        self.assertEqual(kwargs['metadata'], {'test': True})
        self.assertTrue(kwargs['require_signed_urls'])
        self.assertEqual(kwargs['max_file_size'], 1024)
        self.assertEqual(kwargs['allowed_formats'], ['jpeg'])


class CloudflareImageFieldValueTest(TestCase):
    """Test cases for CloudflareImageFieldValue."""

    def test_field_value_creation(self):
        """Test CloudflareImageFieldValue creation."""
        field_value = CloudflareImageFieldValue('test-id')

        self.assertEqual(field_value.cloudflare_id, 'test-id')
        self.assertIsNone(field_value.field)

    def test_field_value_str(self):
        """Test CloudflareImageFieldValue string representation."""
        field_value = CloudflareImageFieldValue('test-id')
        self.assertEqual(str(field_value), 'test-id')

    def test_field_value_bool(self):
        """Test CloudflareImageFieldValue boolean evaluation."""
        field_value = CloudflareImageFieldValue('test-id')
        self.assertTrue(bool(field_value))

        empty_field_value = CloudflareImageFieldValue('')
        self.assertFalse(bool(empty_field_value))

    def test_field_value_equality(self):
        """Test CloudflareImageFieldValue equality comparison."""
        field_value1 = CloudflareImageFieldValue('test-id')
        field_value2 = CloudflareImageFieldValue('test-id')
        field_value3 = CloudflareImageFieldValue('other-id')

        self.assertEqual(field_value1, field_value2)
        self.assertNotEqual(field_value1, field_value3)
        self.assertEqual(field_value1, 'test-id')
        self.assertNotEqual(field_value1, 'other-id')

    def test_get_url_without_cloudflare_image(self):
        """Test get_url method when no CloudflareImage exists."""
        field_value = CloudflareImageFieldValue('test-id')

        # This will generate a URL using the test settings
        url = field_value.get_url()
        self.assertIsNotNone(url)
        if url is not None:
            self.assertIn('test-id', url)

    def test_get_metadata_without_cloudflare_image(self):
        """Test get_metadata method when no CloudflareImage exists."""
        field_value = CloudflareImageFieldValue('test-id')
        metadata = field_value.get_metadata()
        self.assertEqual(metadata, {})

    def test_variants_without_cloudflare_image(self):
        """Test variants property when no CloudflareImage exists."""
        field_value = CloudflareImageFieldValue('test-id')
        variants = field_value.variants
        self.assertEqual(variants, [])

    def test_file_size_without_cloudflare_image(self):
        """Test file_size property when no CloudflareImage exists."""
        field_value = CloudflareImageFieldValue('test-id')
        file_size = field_value.file_size
        self.assertIsNone(file_size)

    def test_filename_without_cloudflare_image(self):
        """Test filename property when no CloudflareImage exists."""
        field_value = CloudflareImageFieldValue('test-id')
        filename = field_value.filename
        self.assertIsNone(filename)

    def test_uploaded_at_without_cloudflare_image(self):
        """Test uploaded_at property when no CloudflareImage exists."""
        field_value = CloudflareImageFieldValue('test-id')
        uploaded_at = field_value.uploaded_at
        self.assertIsNone(uploaded_at)

    def test_is_ready_without_cloudflare_image(self):
        """Test is_ready property when no CloudflareImage exists."""
        field_value = CloudflareImageFieldValue('test-id')
        is_ready = field_value.is_ready
        self.assertFalse(is_ready)


class CloudflareImageFieldIntegrationTest(TestCase):
    """Integration tests with CloudflareImage model."""

    def test_field_value_with_cloudflare_image(self):
        """Test CloudflareImageFieldValue with existing CloudflareImage."""
        from datetime import timedelta

        from django.utils import timezone

        # Create a CloudflareImage instance
        cloudflare_image = CloudflareImage.objects.create(
            cloudflare_id='test-id',
            filename='test.jpg',
            file_size=1024,
            metadata={'category': 'test'},
            variants=['public', 'thumbnail'],
            status='uploaded',
            upload_url='https://example.com/upload',
            expires_at=timezone.now() + timedelta(hours=1)
        )

        # Create field value
        field_value = CloudflareImageFieldValue('test-id')

        # Test that it finds the CloudflareImage
        self.assertEqual(field_value.cloudflare_image, cloudflare_image)
        self.assertEqual(field_value.filename, 'test.jpg')
        self.assertEqual(field_value.file_size, 1024)
        self.assertEqual(field_value.get_metadata(), {'category': 'test'})
        self.assertEqual(field_value.variants, ['public', 'thumbnail'])
        self.assertTrue(field_value.is_ready)
