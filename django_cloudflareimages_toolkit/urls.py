"""
URL configuration for Cloudflare Images Direct Creator Upload.

This module defines the URL patterns for the API endpoints.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CleanupExpiredView,
    CloudflareImageViewSet,
    CreateUploadURLView,
    ImageStatsView,
    WebhookView,
)

app_name = "cloudflare_images"

# Create router for ViewSets
router = DefaultRouter()
router.register(r"images", CloudflareImageViewSet, basename="images")

urlpatterns = [
    # ViewSet routes
    path("api/", include(router.urls)),
    # Custom API endpoints
    path("api/upload-url/", CreateUploadURLView.as_view(), name="create-upload-url"),
    path("api/webhook/", WebhookView.as_view(), name="webhook"),
    path("api/stats/", ImageStatsView.as_view(), name="stats"),
    path("api/cleanup-expired/", CleanupExpiredView.as_view(), name="cleanup-expired"),
]
