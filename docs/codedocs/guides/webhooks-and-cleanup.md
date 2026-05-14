---
title: "Webhooks and Cleanup"
description: "Configure secure webhook processing and clean up expired uploads with the packaged view and management command."
---

This guide covers the operational side of the package: how uploaded images transition into their final state and how stale upload rows are marked or deleted later. The two relevant code paths live in `django_cloudflareimages_toolkit/views.py` and `django_cloudflareimages_toolkit/management/commands/cleanup_expired_images.py`.

<Steps>
<Step>
### Configure the webhook endpoint

```python
from django.urls import include, path

urlpatterns = [
    path("cloudflare-images/", include("django_cloudflareimages_toolkit.urls")),
]
```

That exposes `POST /cloudflare-images/api/webhook/`.

</Step>
<Step>
### Set a webhook secret

```python
CLOUDFLARE_IMAGES = {
    "ACCOUNT_ID": "your-account-id",
    "ACCOUNT_HASH": "your-account-hash",
    "API_TOKEN": "your-api-token",
    "WEBHOOK_SECRET": "shared-secret-from-cloudflare",
}
```

With a configured secret, `WebhookView.post()` rejects missing signatures with `401 Missing signature` before JSON parsing and rejects invalid HMAC signatures with `401 Invalid signature`.

</Step>
<Step>
### Point Cloudflare at your Django endpoint

Configure Cloudflare Images to send events to:

```text
https://your-app.example.com/cloudflare-images/api/webhook/
```

The webhook payload must include at least the Cloudflare image `id`. `WebhookPayloadSerializer` accepts optional `uploaded`, `draft`, `variants`, `metadata`, and `requireSignedURLs` fields.

</Step>
<Step>
### Run periodic cleanup

Use the packaged management command for expired upload URLs:

```bash
python manage.py cleanup_expired_images --dry-run
python manage.py cleanup_expired_images
python manage.py cleanup_expired_images --delete --days 14
```

The command first marks `pending` and `draft` rows whose `expires_at` is in the past as `expired`. With `--delete`, it then deletes rows whose status is already `expired` and whose `updated_at` is older than the requested threshold.

</Step>
</Steps>

Useful production wrapper:

```python
from django.core.management import call_command


def nightly_image_maintenance() -> None:
    call_command("cleanup_expired_images")
    call_command("cleanup_expired_images" delete=True days=30)
```

The request behavior is intentionally strict. Invalid JSON yields HTTP 400, payloads that fail serializer validation also yield HTTP 400, unknown image IDs yield HTTP 404, and unexpected processing failures yield HTTP 500. The tests in `tests/test_webhook_view.py` lock in those branches, so the guide matches the actual contract rather than older informal examples.
