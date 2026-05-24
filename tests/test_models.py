"""
Tests for CloudflareImage model.

Regression coverage for issue #9: ``is_expired`` raised ``TypeError`` when
``expires_at`` was ``None`` (``datetime > None``). A fresh, unsaved instance --
as rendered by the admin *add* form -- has ``expires_at = None``, so reading the
property there returned a 500 instead of behaving like "not expired".
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from django_cloudflareimages_toolkit.models import CloudflareImage


class IsExpiredTest(TestCase):
    """``is_expired`` must not crash when no expiry is set."""

    def test_no_expiry_is_not_expired(self):
        """A record with ``expires_at = None`` is treated as not expired."""
        image = CloudflareImage(expires_at=None)
        self.assertFalse(image.is_expired)

    def test_past_expiry_is_expired(self):
        image = CloudflareImage(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertTrue(image.is_expired)

    def test_future_expiry_is_not_expired(self):
        image = CloudflareImage(expires_at=timezone.now() + timedelta(minutes=1))
        self.assertFalse(image.is_expired)


@pytest.mark.django_db
class AdminAddFormTest(TestCase):
    """The admin add form rendered ``is_expired`` on an unsaved object (#9)."""

    def test_add_form_returns_200(self):
        user = get_user_model().objects.create(
            username="admin", is_staff=True, is_superuser=True
        )
        client = Client(raise_request_exception=True)
        client.force_login(user)

        response = client.get(
            "/admin/django_cloudflareimages_toolkit/cloudflareimage/add/"
        )

        self.assertEqual(response.status_code, 200)
