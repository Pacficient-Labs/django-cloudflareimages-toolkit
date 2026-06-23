"""
Views for Cloudflare Images Toolkit.

This module contains the API views for handling image upload workflows,
transformations, and management operations.
"""

import json
import logging

from django.core.exceptions import FieldError
from django.db.models import Q
from django.db.utils import NotSupportedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from .exceptions import CloudflareImagesError
from .models import CloudflareImage, ImageUploadStatus, ImageUsage
from .serializers import (
    BulkImageDeleteSerializer,
    BulkImageStatusSerializer,
    CloudflareImageSerializer,
    ImageFilterSerializer,
    ImageStatusSerializer,
    ImageUploadLogSerializer,
    ImageUploadRequestSerializer,
    ImageUploadResponseSerializer,
    ImageUsageSerializer,
    WebhookPayloadSerializer,
)
from .services import cloudflare_service
from .settings import cloudflare_settings

logger = logging.getLogger(__name__)

# Django lookup names that collide with ``metadata__<key>=...`` query params.
# Anything in this set after the ``metadata__`` prefix is rejected so a caller
# can't accidentally trigger a JSONField lookup (some, like ``contains``, raise
# NotSupportedError on SQLite and would surface as a 500).
_RESERVED_JSON_LOOKUPS = frozenset(
    {
        "exact",
        "iexact",
        "contains",
        "icontains",
        "in",
        "gt",
        "gte",
        "lt",
        "lte",
        "startswith",
        "istartswith",
        "endswith",
        "iendswith",
        "range",
        "isnull",
        "regex",
        "iregex",
        "has_key",
        "has_keys",
        "has_any_keys",
        "contained_by",
    }
)


def _truthy(value) -> bool:
    """Interpret a query-param string as a boolean."""
    return str(value).lower() in ("1", "true", "yes", "on")


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
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["cloudflare_id", "filename", "original_filename", "creator"]
    ordering_fields = ["created_at", "uploaded_at", "expires_at", "file_size"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Get queryset filtered by user and optional query-param filters.

        Each filter is applied only when its parameter is actually present in the
        request. Boolean serializer fields can otherwise surface in
        ``validated_data`` as ``False`` even when omitted, which would silently
        filter the whole list.
        """
        params = self.request.query_params
        queryset = CloudflareImage.objects.filter(user=self.request.user)

        filter_serializer = ImageFilterSerializer(data=params)
        filter_serializer.is_valid()
        filters = filter_serializer.validated_data

        def provided(name):
            return name in params and name in filters

        if provided("status"):
            queryset = queryset.filter(status=filters["status"])
        if provided("uploaded_after"):
            queryset = queryset.filter(uploaded_at__gte=filters["uploaded_after"])
        if provided("uploaded_before"):
            queryset = queryset.filter(uploaded_at__lte=filters["uploaded_before"])
        if provided("has_variants"):
            if filters["has_variants"]:
                queryset = queryset.exclude(variants=[])
            else:
                queryset = queryset.filter(variants=[])
        if provided("require_signed_urls"):
            queryset = queryset.filter(
                require_signed_urls=filters["require_signed_urls"]
            )
        if provided("filename"):
            term = filters["filename"]
            queryset = queryset.filter(
                Q(filename__icontains=term) | Q(original_filename__icontains=term)
            )
        if provided("creator"):
            queryset = queryset.filter(creator=filters["creator"])
        if "orphaned" in params and filters.get("orphaned"):
            queryset = queryset.filter(usages__isnull=True)

        # Dynamic metadata lookups: ?metadata__<key>=<value>. The trailing
        # segment is treated as a JSON key (which may contain hyphens, dots, or
        # be nested via ``__``), not a Django field lookup. We reject only the
        # final segment matching a JSONField lookup operator (e.g. ``contains``,
        # which would 500 on SQLite) so a stray operator surfaces as a clean 400
        # instead of being silently dropped or crashing.
        for param, value in params.items():
            if not param.startswith("metadata__"):
                continue
            if param.rsplit("__", 1)[-1] in _RESERVED_JSON_LOOKUPS:
                raise DRFValidationError(
                    {param: "Unsupported metadata lookup operator."}
                )
            try:
                queryset = queryset.filter(**{param: value})
            except (FieldError, NotSupportedError) as exc:
                raise DRFValidationError(
                    {param: "Unsupported metadata lookup."}
                ) from exc

        return queryset.distinct()

    @action(
        detail=False,
        methods=["get"],
        # ``.+`` (not ``[^/]+``) so path-style Cloudflare custom IDs like
        # ``products/123/hero`` resolve through this lookup; Cloudflare allows
        # arbitrary slash-containing custom IDs and the ``custom_id`` upload
        # path accepts them, so this lookup must too.
        url_path=r"by-cloudflare-id/(?P<cloudflare_id>.+)",
    )
    def by_cloudflare_id(self, request: Request, cloudflare_id: str = None) -> Response:
        """Look up an image by its Cloudflare ID (instead of the internal UUID)."""
        image = get_object_or_404(self.get_queryset(), cloudflare_id=cloudflare_id)
        serializer = self.get_serializer(image)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def orphans(self, request: Request) -> Response:
        """List images referenced by no content (candidates for cleanup)."""
        queryset = self.filter_queryset(self.get_queryset().filter(usages__isnull=True))
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def usages(self, request: Request, pk=None) -> Response:
        """List the content references for a single image."""
        image = self.get_object()
        serializer = ImageUsageSerializer(image.usages.all(), many=True)
        return Response(serializer.data)

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

    def _delete_image(self, image, force: bool = False):
        """Delete one image from Cloudflare + DB, respecting usage references.

        Returns ``(deleted: bool, detail: dict)``. When the image is still
        referenced by content and ``force`` is False, nothing is deleted and the
        detail reports ``status="in_use"``.
        """
        usage_count = image.usages.count()
        if usage_count and not force:
            return False, {
                "id": str(image.id),
                "cloudflare_id": image.cloudflare_id,
                "status": "in_use",
                "usage_count": usage_count,
            }

        cloudflare_service.delete_image(image)
        detail = {
            "id": str(image.id),
            "cloudflare_id": image.cloudflare_id,
            "status": "deleted",
        }
        image.delete()
        return True, detail

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """Delete from Cloudflare and DB; refuse if referenced (unless ?force)."""
        image = self.get_object()
        force = _truthy(request.query_params.get("force", ""))

        try:
            deleted, _ = self._delete_image(image, force=force)
        except CloudflareImagesError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if not deleted:
            return Response(
                {
                    "error": "Image is still referenced by content.",
                    "usages": ImageUsageSerializer(image.usages.all(), many=True).data,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["delete"])
    def delete_from_cloudflare(self, request: Request, pk=None) -> Response:
        """Alias for DELETE: remove from Cloudflare and local DB (usage-aware)."""
        return self.destroy(request)

    @action(detail=False, methods=["post"])
    def bulk_delete(self, request: Request) -> Response:
        """Delete multiple images (usage-aware) by id and/or cloudflare_id."""
        serializer = BulkImageDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]
        cloudflare_ids = serializer.validated_data["cloudflare_ids"]
        force = serializer.validated_data["force"]

        queryset = self.get_queryset()
        results = []
        seen_pks = set()

        def process(image):
            if image.pk in seen_pks:
                return
            seen_pks.add(image.pk)
            try:
                _, detail = self._delete_image(image, force=force)
            except CloudflareImagesError as e:
                detail = {
                    "id": str(image.id),
                    "cloudflare_id": image.cloudflare_id,
                    "status": "error",
                    "error": str(e),
                }
            results.append(detail)

        by_id = {str(i.id): i for i in queryset.filter(id__in=ids)} if ids else {}
        by_cf = (
            {
                i.cloudflare_id: i
                for i in queryset.filter(cloudflare_id__in=cloudflare_ids)
            }
            if cloudflare_ids
            else {}
        )

        for requested_id in ids:
            image = by_id.get(str(requested_id))
            if image is None:
                results.append({"id": str(requested_id), "status": "not_found"})
            else:
                process(image)

        for cf in cloudflare_ids:
            image = by_cf.get(cf)
            if image is None:
                results.append({"cloudflare_id": cf, "status": "not_found"})
            else:
                process(image)

        return Response({"results": results})

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


class ImageUsageViewSet(ReadOnlyModelViewSet):
    """Read-only ViewSet for browsing image usage references.

    Scoped to the requesting user's images. Staff additionally see usages that
    point at unregistered images (those have no owner). Query params:
    ``content_type`` (``app_label.model``), ``field_name``, ``unregistered``.
    """

    serializer_class = ImageUsageSerializer
    pagination_class = ImagePagination
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["cloudflare_id", "field_name", "object_id"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-updated_at"]

    def get_queryset(self):
        """User-scoped usages, with optional content_type/field/unregistered filters."""
        user = self.request.user
        queryset = ImageUsage.objects.select_related("content_type", "image")
        if not user.is_staff:
            # Scope to the user's own images. Unregistered usages (image is null)
            # have no owner, so they are intentionally visible to staff only — a
            # non-staff `?unregistered=true` request therefore returns nothing.
            queryset = queryset.filter(image__user=user)

        content_type = self.request.query_params.get("content_type")
        if content_type and "." in content_type:
            app_label, model = content_type.split(".", 1)
            queryset = queryset.filter(
                content_type__app_label=app_label, content_type__model=model
            )

        field_name = self.request.query_params.get("field_name")
        if field_name:
            queryset = queryset.filter(field_name=field_name)

        if _truthy(self.request.query_params.get("unregistered", "")):
            queryset = queryset.filter(image__isnull=True)

        return queryset


class CreateUploadURLView(APIView):
    """API view for creating direct upload URLs."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Create a new direct upload URL."""
        serializer = ImageUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # ``filename`` is not a create_direct_upload_url() argument; it is
        # handled separately below. Pop it out before unpacking so passing it
        # through never raises an unexpected-keyword TypeError.
        params = dict(serializer.validated_data)
        filename = params.pop("filename", None)

        try:
            image = cloudflare_service.create_direct_upload_url(
                user=request.user, **params
            )

            # Update filename if provided
            if filename is not None:
                image.original_filename = filename
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
        """Handle incoming webhook from Cloudflare.

        Status codes returned:
          * 200 — payload processed and matched an existing image
          * 400 — payload failed JSON parse OR schema validation
          * 401 — webhook_secret is configured but the request was
                  unauthenticated (missing or invalid signature)
          * 404 — payload was valid but referenced an unknown image
          * 500 — unexpected error while processing a validated payload

        Note that 401 is only emitted when a ``CLOUDFLARE_IMAGES.WEBHOOK_SECRET``
        is configured. Deployments without a secret accept any well-formed
        payload — callers that want enforcement MUST set the secret.
        """
        secret = cloudflare_settings.webhook_secret
        signature = request.META.get("HTTP_X_SIGNATURE") or request.META.get(
            "HTTP_X_CLOUDFLARE_SIGNATURE"
        )

        # A configured secret means signatures are required. Reject before
        # we parse any user-controlled JSON.
        if secret and not signature:
            return HttpResponse(
                "Missing signature", status=status.HTTP_401_UNAUTHORIZED
            )

        if signature and secret:
            if not cloudflare_service.validate_webhook_signature(
                request.body, signature
            ):
                logger.warning("Invalid webhook signature received")
                return HttpResponse(
                    "Invalid signature", status=status.HTTP_401_UNAUTHORIZED
                )

        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponse("Invalid JSON", status=status.HTTP_400_BAD_REQUEST)

        serializer = WebhookPayloadSerializer(data=payload)
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError:
            # A malformed payload is a caller bug, not a server bug. The
            # previous broad ``except Exception`` reported these as 500.
            return HttpResponse("Invalid payload", status=status.HTTP_400_BAD_REQUEST)

        try:
            image = cloudflare_service.process_webhook(payload)
        except Exception:
            logger.exception("Webhook processing error")
            return HttpResponse(
                "Internal server error",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if image:
            return HttpResponse("OK", status=status.HTTP_200_OK)
        return HttpResponse("Image not found", status=status.HTTP_404_NOT_FOUND)


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
            "total_usages": ImageUsage.objects.filter(image__user=request.user).count(),
            "orphaned_images": queryset.filter(usages__isnull=True).count(),
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
