"""
Shared constants for the Cloudflare Images Toolkit.

This module is the single source of truth (SSOT) for literal default values
that would otherwise be written out in several places and silently drift apart.
Keeping them here means a change to a Cloudflare API limit or a default format
list happens in exactly one spot.

These values are intentionally Django-independent so the module can be imported
from anywhere (fields, widgets, services, serializers) without pulling Django in
before it is configured.
"""

# Default image formats accepted by the upload field/widget. Used by
# ``CloudflareImageField`` (its ``__init__`` default *and* the ``deconstruct``
# equality check that decides whether to serialize the kwarg into migrations)
# and by ``CloudflareImageWidget``. Defined once so those callers can never
# disagree about what "the default formats" are.
DEFAULT_ALLOWED_FORMATS = ["jpeg", "png", "gif", "webp"]

# Cloudflare's hard bounds on a direct-upload URL's ``expiry`` window: the URL
# must expire between 2 minutes and 6 hours (360 minutes) in the future. These
# are API limits, not preferences, so they live in one place and are consumed
# by both the service (which clamps to them) and the serializer (which validates
# against them).
MIN_EXPIRY_MINUTES = 2
MAX_EXPIRY_MINUTES = 360

# Cloudflare's maximum ``per_page`` value when listing images. The service
# clamps any caller-supplied page size down to this ceiling.
MAX_LIST_PER_PAGE = 10000
