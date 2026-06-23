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
router.register(r"images", CloudflareImageViewSet, basename="images")
router.register(r"usages", ImageUsageViewSet, basename="usages")
```

### Image usage & lookup routes

| Method & path | Purpose |
|---------------|---------|
| `GET /api/images/by-cloudflare-id/{cloudflare_id}/` | Retrieve an image by its Cloudflare ID. |
| `GET /api/images/{id}/usages/` | List the content references for one image. |
| `GET /api/images/orphans/` | List images referenced by no content. |
| `GET /api/usages/` | Browse usage records (`content_type`, `field_name`, `unregistered` filters). |
| `DELETE /api/images/{id}/` | Delete from Cloudflare + DB; **409** if still referenced unless `?force=true`. |
| `POST /api/images/bulk_delete/` | Usage-aware bulk delete by `ids` / `cloudflare_ids` (+ `force`). |

List filtering on `GET /api/images/` also accepts `filename`, `creator`,
`orphaned=true`, `search=`, `ordering=`, and `metadata__<key>=<value>`.

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
    filter_backends = [SearchFilter, OrderingFilter]

    def get_queryset(self): ...
    def by_cloudflare_id(self, request, cloudflare_id=None) -> Response: ...
    def orphans(self, request) -> Response: ...
    def usages(self, request, pk=None) -> Response: ...
    def check_status(self, request, pk=None) -> Response: ...
    def destroy(self, request, *args, **kwargs) -> Response: ...   # usage-aware
    def delete_from_cloudflare(self, request, pk=None) -> Response: ...
    def bulk_delete(self, request) -> Response: ...                # usage-aware
    def logs(self, request, pk=None) -> Response: ...
    def bulk_status_check(self, request) -> Response: ...
```

`get_queryset()` always scopes results to `request.user` and applies a filter
only when its query parameter is actually present in the request. `destroy()` and
`bulk_delete()` refuse to remove an image that still has `ImageUsage` rows unless
`force` is set.

### `ImageUsageViewSet`

```python
class ImageUsageViewSet(ReadOnlyModelViewSet):
    serializer_class = ImageUsageSerializer
    permission_classes = [permissions.IsAuthenticated]
```

Read-only, scoped to the requesting user's images (staff also see usages whose
image is unregistered). Supports `content_type` (`app_label.model`), `field_name`,
and `unregistered` query params.

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
class BulkImageDeleteSerializer(serializers.Serializer): ...
class ImageUsageSerializer(serializers.ModelSerializer): ...
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
| `ImageFilterSerializer` | `filename` / `creator` / `orphaned` | mixed | Filename `icontains`, exact creator, orphans-only. |
| `BulkImageDeleteSerializer` | `ids` / `cloudflare_ids` / `force` | lists + bool | At least one id list is required. |
| `ImageUsageSerializer` | `content_type` / `content_object` / `is_unregistered` | read-only | Serialised view of an `ImageUsage` row. |
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
