---
title: "Views and Routes"
description: "Reference for the packaged DRF views, serializers, pagination, and URL patterns."
---

Source files: `django_cloudflareimages_toolkit/views.py`, `django_cloudflareimages_toolkit/serializers.py`, `django_cloudflareimages_toolkit/urls.py`

## URL Configuration

Import path:

```python
from django.urls import include, path
```

Packaged routes:

```python
path("cloudflare-images/", include("django_cloudflareimages_toolkit.urls"))
```

Inside the package:

```python
app_name = "cloudflare_images"

urlpatterns = [
    path("api/", include(router.urls)),
    path("api/upload-url/", CreateUploadURLView.as_view() name="create-upload-url"),
    path("api/webhook/", WebhookView.as_view() name="webhook"),
    path("api/stats/", ImageStatsView.as_view() name="stats"),
    path("api/cleanup-expired/", CleanupExpiredView.as_view() name="cleanup-expired"),
]
```

The router registers:

```python
router.register(r"images", CloudflareImageViewSet basename="images")
```

## View classes

### `ImagePagination`

```python
class ImagePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
```

### `CloudflareImageViewSet`

```python
class CloudflareImageViewSet(ModelViewSet):
    serializer_class = CloudflareImageSerializer
    pagination_class = ImagePagination
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self): ...
    def check_status(self, request: Request pk=None) -> Response: ...
    def delete_from_cloudflare(self, request: Request pk=None) -> Response: ...
    def logs(self, request: Request pk=None) -> Response: ...
    def bulk_status_check(self, request: Request) -> Response: ...
```

`get_queryset()` always scopes results to `request.user` and optionally applies filters from `ImageFilterSerializer`.

### `CreateUploadURLView`

```python
class CreateUploadURLView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response: ...
```

### `WebhookView`

```python
class WebhookView(APIView):
    permission_classes = []

    def post(self, request: HttpRequest) -> HttpResponse: ...
```

### `ImageStatsView`

```python
class ImageStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response: ...
```

### `CleanupExpiredView`

```python
class CleanupExpiredView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request: Request) -> Response: ...
```

## Serializer classes

```python
class ImageUploadRequestSerializer(serializers.Serializer): ...
class CloudflareImageSerializer(serializers.ModelSerializer): ...
class ImageUploadResponseSerializer(serializers.Serializer): ...
class ImageStatusSerializer(serializers.Serializer): ...
class ImageUploadLogSerializer(serializers.ModelSerializer): ...
class WebhookPayloadSerializer(serializers.Serializer): ...
class BulkImageStatusSerializer(serializers.Serializer): ...
class ImageFilterSerializer(serializers.Serializer): ...
```

Key request and filtering fields:

| Serializer | Field | Type | Notes |
|------------|-------|------|-------|
| `ImageUploadRequestSerializer` | `custom_id` | `str` | Optional, validated against existing `CloudflareImage.cloudflare_id`. |
| `ImageUploadRequestSerializer` | `metadata` | JSON | Defaults to `{}`. |
| `ImageUploadRequestSerializer` | `require_signed_urls` | `bool` | Optional override. |
| `ImageUploadRequestSerializer` | `expiry_minutes` | `int` | Must be between `2` and `360`. |
| `BulkImageStatusSerializer` | `image_ids` | `list[UUID]` | Max 50 IDs. |
| `ImageFilterSerializer` | `status` | enum | Uses `ImageUploadStatus.choices`. |
| `ImageFilterSerializer` | `uploaded_after` / `uploaded_before` | datetime | Optional upload time range. |
| `ImageFilterSerializer` | `has_variants` | `bool` | Filters empty vs non-empty variants. |
| `WebhookPayloadSerializer` | `id` | `str` | Required Cloudflare image ID. |

## Usage example

```python
response = client.post(
    "/cloudflare-images/api/upload-url/",
    {
        "metadata": {"kind": "avatar"},
        "expiry_minutes": 15,
        "filename": "avatar.png",
    },
    format="json",
)
```

This layer is mostly orchestration. Business logic stays in `CloudflareImagesService`, while serializers define the request and response contract.
