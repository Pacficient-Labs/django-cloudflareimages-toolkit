---
title: "Browser Direct Upload"
description: "Issue one-time upload URLs from Django and let the browser send file bytes directly to Cloudflare."
---

This guide solves the most common integration problem: letting an authenticated browser upload an image without ever receiving your Cloudflare API token. The package already ships the server-side endpoint and serializer for this, so the guide focuses on wiring the browser to the existing API.

<Steps>
<Step>
### Configure Django

```python
INSTALLED_APPS = [
    "rest_framework",
    "django_cloudflareimages_toolkit",
]

CLOUDFLARE_IMAGES = {
    "ACCOUNT_ID": "your-account-id",
    "ACCOUNT_HASH": "your-account-hash",
    "API_TOKEN": "your-api-token",
    "DEFAULT_EXPIRY_MINUTES": 30,
    "REQUIRE_SIGNED_URLS": True,
}
```

</Step>
<Step>
### Expose the packaged routes

```python
from django.urls import include, path

urlpatterns = [
    path("cloudflare-images/", include("django_cloudflareimages_toolkit.urls")),
]
```

The upload URL endpoint is now `POST /cloudflare-images/api/upload-url/`.

</Step>
<Step>
### Request a one-time upload URL from your frontend

```html
<form id="avatar-form">
  <input id="avatar-file" type="file" accept="image/*">
  <button type="submit">Upload avatar</button>
</form>
<pre id="status"></pre>
```

```js
const form = document.getElementById("avatar-form");
const fileInput = document.getElementById("avatar-file");
const statusNode = document.getElementById("status");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  const createResponse = await fetch("/cloudflare-images/api/upload-url/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      metadata: { kind: "avatar" },
      require_signed_urls: false,
      expiry_minutes: 15,
      filename: file.name,
    }),
  });

  const uploadConfig = await createResponse.json();
  if (!createResponse.ok) {
    statusNode.textContent = JSON.stringify(uploadConfig, null, 2);
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  const uploadResponse = await fetch(uploadConfig.upload_url, {
    method: "POST",
    body: formData,
  });

  statusNode.textContent = uploadResponse.ok
    ? `Upload sent for ${uploadConfig.cloudflare_id}`
    : `Cloudflare rejected upload: ${uploadResponse.status}`;
});

function getCookie(name) {
  return document.cookie
    .split(";")
    .map((item) => item.trim().split("="))
    .find(([key]) => key === name)?.[1] || "";
}
```

</Step>
<Step>
### Reconcile the local row

Use webhooks for normal completion, or poll on demand:

```python
from django_cloudflareimages_toolkit.models import CloudflareImage
from django_cloudflareimages_toolkit.services import cloudflare_service


def sync_upload(cloudflare_id: str) -> CloudflareImage:
    image = CloudflareImage.objects.get(cloudflare_id=cloudflare_id)
    cloudflare_service.check_image_status(image)
    image.refresh_from_db()
    return image
```

</Step>
</Steps>

Complete result:

```python
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from django_cloudflareimages_toolkit.models import CloudflareImage


@login_required
def avatar_status(request, cloudflare_id: str) -> JsonResponse:
    image = CloudflareImage.objects.get(
        user=request.user,
        cloudflare_id=cloudflare_id,
    )
    return JsonResponse(
        {
            "status": image.status,
            "public_url": image.public_url,
            "thumbnail_url": image.thumbnail_url,
        }
    )
```

This guide intentionally uses the packaged endpoint instead of re-implementing upload URL generation. If you need custom authorization logic, wrap `cloudflare_service.create_direct_upload_url()` in your own view but keep the same server-issued, browser-uploaded flow.
