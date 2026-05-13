"""
Tests for WebhookView.

Regression coverage for the two bugs fixed by
fix/webhook-signature-and-payload-errors:

  1. With a configured webhook secret, a request that arrives WITHOUT a
     signature header must be rejected as 401. Previously the view only
     ran signature validation when *both* header and secret were present,
     which let unsigned requests slip past the gate.

  2. A malformed / partially-valid payload (one that fails
     ``WebhookPayloadSerializer.is_valid(raise_exception=True)``) must
     surface as 400. Previously the broad ``except Exception`` swallowed
     the DRF ValidationError and returned 500, which made operational
     observability worse and masked caller bugs as server bugs.

Note on settings overrides: ``CloudflareImagesSettings`` snapshots the
``CLOUDFLARE_IMAGES`` dict at construction time, so the module-level
``cloudflare_settings`` singleton doesn't react to ``override_settings``.
We patch the singleton's ``_settings`` directly via ``monkeypatch`` to
exercise the no-secret branch.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from django.test import Client
from rest_framework import status

from django_cloudflareimages_toolkit.settings import cloudflare_settings


WEBHOOK_URL = "/cloudflare-images/api/webhook/"
SECRET = "test-webhook-secret"


def _sign(payload: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture
def disabled_secret(monkeypatch):
    """Clear ``WEBHOOK_SECRET`` for a single test.

    ``override_settings`` doesn't reach the cached settings singleton, so
    we patch the dict it reads from directly.
    """
    monkeypatch.setitem(cloudflare_settings._settings, "WEBHOOK_SECRET", "")


@pytest.fixture
def enabled_secret(monkeypatch):
    """Force ``WEBHOOK_SECRET`` for tests that assert signature enforcement."""
    monkeypatch.setitem(cloudflare_settings._settings, "WEBHOOK_SECRET", SECRET)


@pytest.mark.django_db
class TestWebhookSignatureGate:
    """Signature-handling matrix when a webhook_secret is configured."""

    def test_missing_signature_with_secret_set_returns_401(
        self, client: Client, enabled_secret
    ):
        """Configured secret + missing header = 401, NOT 200 / 5xx.

        Previously this case fell through the gate because the upstream
        guard was ``if signature and webhook_secret`` — both had to be
        truthy. An unauthenticated caller could ship any payload past
        validation. Regression-locked here.
        """
        body = json.dumps({"event": "test"}).encode()
        response = client.post(
            WEBHOOK_URL, data=body, content_type="application/json"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_signature_with_secret_set_returns_401(
        self, client: Client, enabled_secret
    ):
        body = json.dumps({"event": "test"}).encode()
        response = client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_SIGNATURE="sha256=deadbeef",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch(
        "django_cloudflareimages_toolkit.services.cloudflare_service.process_webhook",
        return_value=None,
    )
    @pytest.mark.parametrize(
        "signature_header",
        ["HTTP_X_SIGNATURE", "HTTP_X_CLOUDFLARE_SIGNATURE"],
    )
    def test_valid_signature_proceeds_to_processing(
        self, mock_process, client: Client, enabled_secret, signature_header: str
    ):
        # ``id`` is the only required WebhookPayloadSerializer field;
        # everything else is optional.
        body = json.dumps({"id": "abc123"}).encode()
        response = client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            **{signature_header: _sign(body)},
        )
        # Signature accepted, payload validated, processing called. The
        # mock returns None so the view answers 404 — but the gate
        # didn't short-circuit with a 4xx auth response.
        assert response.status_code != status.HTTP_401_UNAUTHORIZED
        mock_process.assert_called_once()


@pytest.mark.django_db
class TestWebhookPayloadValidation:
    """Deployments that haven't configured a secret accept any payload —
    we still need to fail cleanly on garbage input."""

    def test_invalid_payload_returns_400_not_500(
        self, client: Client, disabled_secret
    ):
        """Malformed payload = 400, NOT 500.

        WebhookPayloadSerializer.is_valid(raise_exception=True) raises
        DRFValidationError. Previously this was swallowed by
        ``except Exception`` and reported as 500. Caller bugs should be
        observable as caller bugs.
        """
        # ``{"event": "test"}`` lacks the required ``id`` field and will
        # fail serializer validation.
        body = json.dumps({"event": "test"}).encode()
        response = client.post(
            WEBHOOK_URL, data=body, content_type="application/json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_json_returns_400(self, client: Client, disabled_secret):
        response = client.post(
            WEBHOOK_URL,
            data=b"this is not json",
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
