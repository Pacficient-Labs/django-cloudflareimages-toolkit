Patterns & Recipes
==================

This guide covers two operational patterns that come up repeatedly when
running ``django-cloudflareimages-toolkit`` in production but that the
package itself deliberately does **not** bake in: resilience against
Cloudflare API outages, and image-access authorization (including
role-based permissions and dynamic watermarking).

Both are buildable on top of the package's existing primitives —
``cloudflare_service``, ``CloudflareImage``, ``CloudflareImageTransform``,
and standard DRF permission classes. The recipes below show concrete,
copy-pasteable code.

.. contents::
   :local:
   :depth: 2


Resilience: handling a Cloudflare Images API outage
---------------------------------------------------

``cloudflare_service`` makes synchronous HTTPS calls against
``api.cloudflare.com``. When the Cloudflare control plane is degraded or
unreachable, those calls fail and raise
``django_cloudflareimages_toolkit.exceptions.CloudflareImagesError`` —
the package surfaces the error rather than hiding it. The patterns below
show how to layer retries, a circuit breaker, and graceful degradation
on top of those primitives without forking the package.


Retry with exponential backoff
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Transient Cloudflare blips (5xx, connection resets, DNS hiccups) usually
clear within a few seconds. Wrap each service call in a backoff loop and
log every retry so operators can spot a real outage versus normal noise.

.. code-block:: python

   import logging
   import random
   import time
   from functools import wraps
   from typing import Callable, TypeVar, ParamSpec

   from django_cloudflareimages_toolkit.exceptions import CloudflareImagesError

   logger = logging.getLogger(__name__)
   P = ParamSpec("P")
   T = TypeVar("T")


   def retry_cloudflare(
       attempts: int = 4,
       base_delay: float = 0.5,
       max_delay: float = 8.0,
   ) -> Callable[[Callable[P, T]], Callable[P, T]]:
       """Retry a Cloudflare call with capped exponential backoff + jitter.

       Only retries ``CloudflareImagesError`` — caller bugs (TypeError,
       ValueError, etc.) bubble immediately so they fail loudly in tests.
       """

       def decorator(fn: Callable[P, T]) -> Callable[P, T]:
           @wraps(fn)
           def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
               last_exc: CloudflareImagesError | None = None
               for attempt in range(1, attempts + 1):
                   try:
                       return fn(*args, **kwargs)
                   except CloudflareImagesError as exc:
                       last_exc = exc
                       if attempt == attempts:
                           break
                       delay = min(
                           max_delay,
                           base_delay * (2 ** (attempt - 1)),
                       )
                       # Decorrelated jitter so concurrent retriers don't
                       # all hammer Cloudflare at the same moment.
                       delay = random.uniform(base_delay, delay)
                       logger.warning(
                           "Cloudflare call failed (attempt %d/%d), retrying in %.2fs: %s",
                           attempt,
                           attempts,
                           delay,
                           exc,
                       )
                       time.sleep(delay)
               assert last_exc is not None
               raise last_exc

           return wrapper

       return decorator


   from django_cloudflareimages_toolkit.services import cloudflare_service

   @retry_cloudflare(attempts=4, base_delay=0.5, max_delay=8.0)
   def create_upload_url_with_retry(user, **kwargs):
       return cloudflare_service.create_direct_upload_url(user=user, **kwargs)


Circuit breaker — fail fast during a real outage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Retries help with blips, but during a multi-minute Cloudflare outage they
just multiply the load on a struggling control plane and slow down every
request thread. A circuit breaker trips after consecutive failures, fails
calls immediately for a cooldown window, then probes to see if the API
is back.

The example uses Django's cache as the shared state store, which means
it works across processes and Gunicorn workers without extra infra.

.. code-block:: python

   from django.core.cache import cache
   from django_cloudflareimages_toolkit.exceptions import CloudflareImagesError

   _CB_KEY = "cf_images:circuit_state"
   _CB_FAILURE_THRESHOLD = 5
   _CB_OPEN_SECONDS = 30


   class CircuitOpen(CloudflareImagesError):
       """Raised when the breaker is open. Subclasses CloudflareImagesError
       so existing exception handlers catch it transparently."""


   def call_with_circuit_breaker(fn, /, *args, **kwargs):
       state = cache.get(_CB_KEY) or {"failures": 0, "open_until": 0}

       import time as _t
       now = _t.time()
       if state["open_until"] > now:
           raise CircuitOpen("Cloudflare Images breaker is open")

       try:
           result = fn(*args, **kwargs)
       except CloudflareImagesError:
           failures = state["failures"] + 1
           if failures >= _CB_FAILURE_THRESHOLD:
               cache.set(_CB_KEY, {"failures": 0, "open_until": now + _CB_OPEN_SECONDS}, timeout=_CB_OPEN_SECONDS + 5)
           else:
               cache.set(_CB_KEY, {"failures": failures, "open_until": 0}, timeout=300)
           raise
       else:
           if state["failures"]:
               cache.set(_CB_KEY, {"failures": 0, "open_until": 0}, timeout=300)
           return result


Graceful degradation in the request path
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For *read* paths (e.g. rendering a page that shows a user's avatar),
treat the Cloudflare URL as a cache-warmed asset and fall back to a
placeholder when both the cache and the API are unavailable. Don't make
end users wait on a degraded control plane.

.. code-block:: python

   from django.core.cache import cache
   from django_cloudflareimages_toolkit.models import CloudflareImage
   from django_cloudflareimages_toolkit.exceptions import CloudflareImagesError

   PLACEHOLDER_URL = "/static/img/avatar-placeholder.png"


   def avatar_url_for(user) -> str:
       cache_key = f"avatar:{user.pk}"
       cached = cache.get(cache_key)
       if cached:
           return cached

       try:
           image = CloudflareImage.objects.filter(user=user, status="uploaded").first()
           if image and image.is_uploaded:
               url = image.public_url or image.get_variant_url("avatar")
               cache.set(cache_key, url, timeout=300)
               return url
       except CloudflareImagesError:
           # Cloudflare is degraded; serve the placeholder rather than
           # blocking the page render. The next cache miss will retry.
           pass

       return PLACEHOLDER_URL


Failure handling for direct creator uploads
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Direct creator uploads have three failure modes worth handling
explicitly. Each maps to a concrete recovery path:

1. **URL provisioning fails** (`create_direct_upload_url` raises
   ``CloudflareImagesError``) — Cloudflare API was unreachable or
   refused the request. The user clicked "upload" and got nothing.
2. **Upload POST fails** (the browser or server-side ``requests.post``
   to ``image.upload_url`` errors out) — Cloudflare's edge accepted
   the URL but couldn't accept the bytes. Likely transient.
3. **Cloudflare rejects the file after upload** (webhook delivers a
   failure event, ``check_image_status`` returns ``status="failed"``)
   — Cloudflare took the bytes but processing failed (corrupt JPEG,
   unsupported format, too large, etc.). Not retryable.

The pattern below combines retry, user feedback, and a local fallback
into a single end-to-end recipe.

.. code-block:: python

   import logging
   from typing import Any

   import requests
   from django.contrib import messages
   from django.core.cache import cache
   from django.db import transaction

   from django_cloudflareimages_toolkit.exceptions import CloudflareImagesError
   from django_cloudflareimages_toolkit.services import cloudflare_service

   logger = logging.getLogger(__name__)


   @retry_cloudflare(attempts=4, base_delay=0.5, max_delay=8.0)
   def _provision_upload_slot(user, metadata):
       return cloudflare_service.create_direct_upload_url(
           user=user, metadata=metadata, expiry_minutes=30
       )


   def _post_bytes(upload_url: str, blob: bytes, name: str) -> None:
       """Server-side POST with a short retry on transient network errors."""
       last_exc: Exception | None = None
       for attempt in range(1, 4):
           try:
               r = requests.post(
                   upload_url,
                   files={"file": (name, blob, "application/octet-stream")},
                   timeout=30,
               )
               r.raise_for_status()
               return
           except requests.RequestException as exc:
               last_exc = exc
               if attempt < 3:
                   time.sleep(0.5 * (2 ** (attempt - 1)))
       assert last_exc is not None
       raise last_exc


   def upload_with_recovery(request, blob: bytes, filename: str):
       """End-to-end upload that notifies the user on every failure mode
       and persists local state regardless of whether Cloudflare succeeds.
       """
       # Step 1: provision the upload slot.
       try:
           image = _provision_upload_slot(
               request.user,
               metadata={"source": "user_upload", "ip": _client_ip(request)},
           )
       except CloudflareImagesError as exc:
           logger.exception("Cloudflare URL provisioning failed")
           messages.error(
               request,
               "We're having trouble reaching our image host. "
               "Your file was NOT uploaded. Please try again in a few minutes.",
           )
           _record_failed_attempt(request.user, filename, reason="provision")
           return None

       # Step 2: post the bytes.
       try:
           _post_bytes(image.upload_url, blob, image.cloudflare_id)
       except requests.RequestException as exc:
           logger.exception("Cloudflare upload POST failed")
           messages.warning(
               request,
               "Upload couldn't be completed. We've saved a draft locally — "
               "you can retry without re-selecting your file.",
           )
           _store_local_fallback(request.user, image, blob, filename)
           return image

       # Step 3: confirm Cloudflare accepted the file.
       try:
           cloudflare_service.check_image_status(image)
           image.refresh_from_db()
       except CloudflareImagesError:
           # Status check failed but the bytes were delivered; the
           # webhook will eventually move the row to UPLOADED or FAILED.
           # Don't block the user response on this.
           pass

       if image.status == "failed":
           messages.error(
               request,
               "Your image was rejected (unsupported format or corrupt file). "
               "Please pick a different file.",
           )
           return image

       messages.success(request, "Image uploaded successfully.")
       return image


   def _store_local_fallback(user, image, blob: bytes, filename: str) -> None:
       """Persist the bytes so the user can retry without re-selecting.

       Stash in cache (small footprint, expires automatically) and link
       to the CloudflareImage row so the retry handler can pick up where
       this attempt left off.
       """
       key = f"upload_fallback:{user.pk}:{image.pk}"
       cache.set(key, {"blob": blob, "filename": filename}, timeout=3600)


   def retry_failed_upload(request, image_id: int):
       key = f"upload_fallback:{request.user.pk}:{image_id}"
       data = cache.get(key)
       if not data:
           messages.error(request, "Your previous upload has expired — please re-select your file.")
           return None
       image = cloudflare_service.create_direct_upload_url(user=request.user)
       _post_bytes(image.upload_url, data["blob"], data["filename"])
       cache.delete(key)
       return image

Key behaviors:

- **User notification is per failure mode.** Provisioning failure says
  "we couldn't reach our image host"; upload failure says "we saved a
  draft, retry"; rejection says "your file is the problem." That's
  three distinct user states with three distinct recovery paths.
- **Retries are layered** — ``_provision_upload_slot`` retries the
  Cloudflare control plane, ``_post_bytes`` retries the edge upload,
  and ``check_image_status`` is *not* retried because the webhook will
  drive the same state machine asynchronously.
- **Local fallback** uses Django's cache rather than disk so it
  expires automatically and works across Gunicorn workers. For larger
  files, swap the cache for an S3-backed staging bucket.
- **The CloudflareImage row is always persisted** even when the POST
  fails — that gives the retry handler a stable anchor and lets
  operators see how many uploads stalled at each step (a useful
  signal for a Cloudflare degradation dashboard).

Safely registering a client-supplied cloudflare_id
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a browser uploads directly to Cloudflare and then reports the
``cloudflare_id`` back to your server, treat that id as untrusted input. It
may not exist, may still be a draft, or may belong to another user — and
calling ``CloudflareImage.objects.get_or_create(cloudflare_id=<client value>)``
directly leaves a bare local row that does not correspond to a real image.

Use ``CloudflareImage.objects.register_uploaded`` instead. It fetches the
image from Cloudflare, confirms it exists and that its draft state is
cleared, then creates (or returns) the local record populated with status,
variants, metadata, and creator. On failure it raises before any local row
is created.

.. code-block:: python

   from django_cloudflareimages_toolkit import (
       CloudflareImage, ImageNotFoundError, ImageNotReadyError,
   )

   try:
       image = CloudflareImage.objects.register_uploaded(
           cloudflare_id, user=request.user
       )
   except ImageNotFoundError:
       ...  # id does not exist in Cloudflare
   except ImageNotReadyError:
       ...  # exists but upload not completed (still a draft)

When you tag uploads with ``creator``, pass ``expected_creator`` to enforce
ownership — the Cloudflare ``creator`` must match or ``ImageOwnershipError`` is
raised before any row is created:

.. code-block:: python

   from django_cloudflareimages_toolkit import ImageOwnershipError

   try:
       image = CloudflareImage.objects.register_uploaded(
           cloudflare_id, user=request.user, expected_creator=str(request.user.pk)
       )
   except ImageOwnershipError:
       ...  # the id belongs to a different creator

Because ``register_uploaded`` makes a synchronous call to Cloudflare, it is
a natural fit for the retry and circuit-breaker wrappers above when the id
is registered from a hot request path.

Distributed processing pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For *write* paths (uploads, status checks, deletions), push the work
through a task queue (Celery, RQ, Dramatiq) so the request handler
returns quickly and retries happen out-of-band against Cloudflare:

.. code-block:: python

   # tasks.py
   from celery import shared_task
   from django_cloudflareimages_toolkit.services import cloudflare_service
   from django_cloudflareimages_toolkit.exceptions import CloudflareImagesError

   @shared_task(
       bind=True,
       autoretry_for=(CloudflareImagesError,),
       retry_backoff=True,
       retry_backoff_max=300,
       retry_jitter=True,
       max_retries=10,
   )
   def check_image_status_async(self, image_id: int) -> None:
       from django_cloudflareimages_toolkit.models import CloudflareImage
       image = CloudflareImage.objects.get(pk=image_id)
       cloudflare_service.check_image_status(image)

The view enqueues the task and returns immediately; the worker performs
the polling with Celery's built-in retry backoff. If Cloudflare is down
for an hour the tasks stay queued and resume on recovery instead of
failing user-visible requests.


Authorization: per-user image access + dynamic watermarking
-----------------------------------------------------------

The package's bundled viewsets default to ``IsAuthenticated`` and only
list images belonging to ``request.user``. Production systems often need
more: tenant-scoped sharing, viewer roles, expiring signed URLs, and
watermarks that vary by who's looking. This is straightforward to layer
on top of the existing primitives.


Object-level permissions via DRF
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Subclass the bundled viewset and plug in a custom ``BasePermission``.
The permission can consult Django groups, your own ``Tenant`` model, or
any other context.

.. code-block:: python

   from rest_framework.permissions import BasePermission, IsAuthenticated
   from django_cloudflareimages_toolkit.views import CloudflareImageViewSet

   class CanAccessImage(BasePermission):
       """RBAC: image owner OR member of an authorized viewer group."""

       def has_permission(self, request, view) -> bool:
           # Block bulk-listing endpoints to non-owners; the viewset's
           # get_queryset already scopes to request.user, so this is
           # belt-and-suspenders for any custom list views you add.
           return request.user.is_authenticated

       def has_object_permission(self, request, view, obj) -> bool:
           if obj.user_id == request.user.id:
               return True
           # Group-based viewer role
           if request.user.groups.filter(name="image_viewer").exists():
               return True
           # Tenant-scoped sharing (assumes obj.metadata holds {"tenant": ...})
           tenant_id = (obj.metadata or {}).get("tenant")
           if tenant_id and getattr(request.user, "tenant_id", None) == tenant_id:
               return True
           return False


   class GovernedCloudflareImageViewSet(CloudflareImageViewSet):
       permission_classes = [IsAuthenticated, CanAccessImage]


Wire ``GovernedCloudflareImageViewSet`` into your URL conf instead of
the default one. The viewset's ``get_queryset`` already restricts list
results to the requesting user; the custom permission gates direct
detail/update/delete attempts.


Authorization middleware (alternative wiring)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If your access policy spans many endpoints (not just the bundled
viewset), Django middleware can enforce it before the request even
reaches a view:

.. code-block:: python

   import re
   from django.http import JsonResponse

   _IMAGE_PATH = re.compile(r"^/cloudflare-images/api/images/(?P<pk>\d+)/")


   class CloudflareImageAccessMiddleware:
       """Reject access to image detail routes the caller can't see."""

       def __init__(self, get_response):
           self.get_response = get_response

       def __call__(self, request):
           match = _IMAGE_PATH.match(request.path)
           if not match or not request.user.is_authenticated:
               return self.get_response(request)

           from django_cloudflareimages_toolkit.models import CloudflareImage
           pk = int(match.group("pk"))
           try:
               image = CloudflareImage.objects.only("user_id", "metadata").get(pk=pk)
           except CloudflareImage.DoesNotExist:
               return self.get_response(request)

           if image.user_id == request.user.id:
               return self.get_response(request)
           if request.user.groups.filter(name="image_viewer").exists():
               return self.get_response(request)
           return JsonResponse({"detail": "Forbidden"}, status=403)


   # settings.py
   MIDDLEWARE = [
       # ... your other middleware ...
       "myapp.middleware.CloudflareImageAccessMiddleware",
   ]

The middleware is the right tool when authorization needs to apply to
template views, HTMX partials, or other non-DRF surfaces alongside the
JSON API. For pure DRF, the permission class above is lighter-weight.


Dynamic watermarking based on user context
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Cloudflare Images supports watermark transformations natively
(``draw=`` parameter). Use ``CloudflareImageTransform`` to build a URL
that injects a watermark identifying the viewer — useful for leak-
attribution on shared / paid content.

.. code-block:: python

   from django_cloudflareimages_toolkit.transformations import (
       CloudflareImageTransform,
   )

   ACCOUNT_HASH = "your-account-hash"
   WATERMARK_IMAGE_ID = "static-watermark-asset-id"

   def watermarked_url_for(image, viewer) -> str:
       """Return a Cloudflare delivery URL with a viewer-specific
       watermark drawn over the bottom-right corner."""
       transform = (
           CloudflareImageTransform()
           .width(1600)
           .quality(85)
           .format("auto")
           # `draw` overlays another Cloudflare-hosted image; use a
           # per-tier watermark asset so paid users see a small,
           # unobtrusive mark while free users see a larger one.
           .draw(
               WATERMARK_IMAGE_ID,
               opacity=0.4 if viewer.is_premium else 0.7,
               bottom=24,
               right=24,
               width=160 if viewer.is_premium else 240,
           )
       )
       return transform.url(ACCOUNT_HASH, image.cloudflare_id, variant="public")


For text watermarks (e.g. ``"shared by {viewer.email} on {date}"``), pre-
render them as transparent PNGs and upload them as Cloudflare Images
once; reference them in ``draw`` by ``cloudflare_id`` as above. The
toolkit does **not** render text watermarks server-side; Cloudflare's
``draw`` transformation expects an existing image asset.


Combining all three: signed + scoped + watermarked URLs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For shared previews that should expire and that identify the viewer:

.. code-block:: python

   def shared_preview_url(image: "CloudflareImage", viewer) -> str:
       # 1. Verify access (raise PermissionDenied if not allowed)
       check_can_view(image, viewer)

       # 2. Get a signed, short-lived URL for the base image
       base_url = image.get_signed_url(variant="public", expiry=300)

       # 3. Layer the watermark transformation on top
       return watermarked_url_for(image, viewer)

You can combine signed URLs with transformations because Cloudflare
Images applies transformations on the signed delivery URL before
verifying the signature. Test in your environment that your signed-URL
expiry matches the cache TTL you're handing to clients.
