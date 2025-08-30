"""
Views for Cloudflare Images Toolkit.

This module contains the API views for handling image upload workflows,
transformations, and management operations.
"""

import json
import logging

from django.http import HttpRequest, HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from .exceptions import CloudflareImagesError
from .models import CloudflareImage, ImageUploadStatus
from .serializers import (
    BulkImageStatusSerializer,
    CloudflareImageSerializer,
    ImageFilterSerializer,
    ImageStatusSerializer,
    ImageUploadLogSerializer,
    ImageUploadRequestSerializer,
    ImageUploadResponseSerializer,
    WebhookPayloadSerializer,
)
from .services import cloudflare_service
from .settings import cloudflare_settings

logger = logging.getLogger(__name__)


class ImagePagination(PageNumberPagination):
    """Custom pagination for image listings."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class CloudflareImageViewSet(ModelViewSet):
    """ViewSet for managing Cloudflare images."""

    serializer_class = CloudflareImageSerializer
    pagination_class = ImagePagination
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get queryset filtered by user and optional filters."""
        queryset = CloudflareImage.objects.filter(user=self.request.user)

        # Apply filters from query parameters
        filter_serializer = ImageFilterSerializer(data=self.request.query_params)
        if filter_serializer.is_valid():
            filters = filter_serializer.validated_data

            if filters and "status" in filters:
                queryset = queryset.filter(status=filters["status"])

            if filters and "uploaded_after" in filters:
                queryset = queryset.filter(uploaded_at__gte=filters["uploaded_after"])

            if filters and "uploaded_before" in filters:
                queryset = queryset.filter(uploaded_at__lte=filters["uploaded_before"])

            if filters and "has_variants" in filters:
                if filters["has_variants"]:
                    queryset = queryset.exclude(variants=[])
                else:
                    queryset = queryset.filter(variants=[])

            if filters and "require_signed_urls" in filters:
                queryset = queryset.filter(
                    require_signed_urls=filters["require_signed_urls"]
                )

        return queryset.order_by("-created_at")

    @action(detail=True, methods=["post"])
    def check_status(self, request: Request, pk=None) -> Response:
        """Check the current status of an image upload."""
        image = self.get_object()

        try:
            cloudflare_service.check_image_status(image)
            serializer = ImageStatusSerializer(
                data={
                    "id": image.id,
                    "cloudflare_id": image.cloudflare_id,
                    "status": image.status,
                    "uploaded_at": image.uploaded_at,
                    "variants": image.variants,
                    "public_url": image.public_url,
                    "thumbnail_url": image.thumbnail_url,
                    "is_uploaded": image.is_uploaded,
                    "is_expired": image.is_expired,
                }
            )
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data)

        except CloudflareImagesError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["delete"])
    def delete_from_cloudflare(self, request: Request, pk=None) -> Response:
        """Delete image from Cloudflare and local database."""
        image = self.get_object()

        try:
            cloudflare_service.delete_image(image)
            image.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        except CloudflareImagesError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"])
    def logs(self, request: Request, pk=None) -> Response:
        """Get upload logs for an image."""
        image = self.get_object()
        logs = image.logs.all()
        serializer = ImageUploadLogSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def bulk_status_check(self, request: Request) -> Response:
        """Check status for multiple images."""
        serializer = BulkImageStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        image_ids = serializer.validated_data["image_ids"]
        images = self.get_queryset().filter(id__in=image_ids)

        results = []
        for image in images:
            try:
                cloudflare_service.check_image_status(image)
                results.append(
                    {
                        "id": image.id,
                        "cloudflare_id": image.cloudflare_id,
                        "status": image.status,
                        "uploaded_at": image.uploaded_at,
                        "variants": image.variants,
                        "public_url": image.public_url,
                        "thumbnail_url": image.thumbnail_url,
                        "is_uploaded": image.is_uploaded,
                        "is_expired": image.is_expired,
                    }
                )
            except CloudflareImagesError as e:
                results.append(
                    {
                        "id": image.id,
                        "cloudflare_id": image.cloudflare_id,
                        "error": str(e),
                    }
                )

        return Response({"results": results})


class CreateUploadURLView(APIView):
    """API view for creating direct upload URLs."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Create a new direct upload URL."""
        serializer = ImageUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            image = cloudflare_service.create_direct_upload_url(
                user=request.user, **serializer.validated_data
            )

            # Update filename if provided
            if "filename" in serializer.validated_data:
                image.original_filename = serializer.validated_data["filename"]
                image.save()

            response_serializer = ImageUploadResponseSerializer(
                data={
                    "id": image.id,
                    "cloudflare_id": image.cloudflare_id,
                    "upload_url": image.upload_url,
                    "expires_at": image.expires_at,
                    "status": image.status,
                }
            )
            response_serializer.is_valid(raise_exception=True)

            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except CloudflareImagesError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(APIView):
    """API view for handling Cloudflare webhooks."""

    permission_classes = []  # Webhooks don't use standard authentication

    def post(self, request: HttpRequest) -> HttpResponse:
        """Handle incoming webhook from Cloudflare."""
        try:
            # Validate webhook signature if configured
            # Cloudflare sends signatures in X-Signature header
            signature = request.META.get("HTTP_X_SIGNATURE") or request.META.get(
                "HTTP_X_CLOUDFLARE_SIGNATURE"
            )
            if signature and cloudflare_settings.webhook_secret:
                if not cloudflare_service.validate_webhook_signature(
                    request.body, signature
                ):
                    logger.warning("Invalid webhook signature received")
                    return HttpResponse(
                        "Invalid signature", status=status.HTTP_401_UNAUTHORIZED
                    )

            # Parse and validate payload
            payload = json.loads(request.body)
            serializer = WebhookPayloadSerializer(data=payload)
            serializer.is_valid(raise_exception=True)

            # Process webhook
            image = cloudflare_service.process_webhook(payload)

            if image:
                return HttpResponse("OK", status=status.HTTP_200_OK)
            else:
                return HttpResponse("Image not found", status=status.HTTP_404_NOT_FOUND)

        except json.JSONDecodeError:
            return HttpResponse("Invalid JSON", status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            return HttpResponse(
                "Internal server error", status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ImageStatsView(APIView):
    """API view for image upload statistics."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Get image upload statistics for the user."""
        queryset = CloudflareImage.objects.filter(user=request.user)

        stats = {
            "total_images": queryset.count(),
            "uploaded_images": queryset.filter(
                status=ImageUploadStatus.UPLOADED
            ).count(),
            "pending_images": queryset.filter(status=ImageUploadStatus.PENDING).count(),
            "draft_images": queryset.filter(status=ImageUploadStatus.DRAFT).count(),
            "failed_images": queryset.filter(status=ImageUploadStatus.FAILED).count(),
            "expired_images": queryset.filter(status=ImageUploadStatus.EXPIRED).count(),
            "total_file_size": sum(
                img.file_size or 0 for img in queryset.filter(file_size__isnull=False)
            ),
            "images_with_signed_urls": queryset.filter(
                require_signed_urls=True
            ).count(),
        }

        return Response(stats)


class CleanupExpiredView(APIView):
    """API view for cleaning up expired upload URLs."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request: Request) -> Response:
        """Clean up expired upload URLs."""
        from django.utils import timezone

        expired_images = CloudflareImage.objects.filter(
            expires_at__lt=timezone.now(),
            status__in=[ImageUploadStatus.PENDING, ImageUploadStatus.DRAFT],
        )

        count = expired_images.count()
        expired_images.update(status=ImageUploadStatus.EXPIRED)

        return Response(
            {"message": f"Marked {count} expired images", "expired_count": count}
        )
