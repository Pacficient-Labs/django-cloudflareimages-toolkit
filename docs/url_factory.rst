Image URL Factory
=================

The image URL factory is the single source of truth for constructing,
recognizing, extracting from, and rewriting Cloudflare Images delivery URLs.
Every place the toolkit produces a delivery URL routes through it, so a single
``DELIVERY_URL`` setting (see :doc:`configuration`) controls the delivery domain
for the whole application.

Why it exists
-------------

Cloudflare returns image variant URLs on its shared ``imagedelivery.net`` domain,
and historically the toolkit hardcoded that host in several places. The factory
centralizes that logic so admins can serve images from an alternate domain — a
native custom domain or a Cloudflare Worker reverse-proxy — without changing
application code.

The singleton
-------------

A ready-to-use instance is exported from the package root:

.. code-block:: python

   from django_cloudflareimages_toolkit import image_url_factory

It reads settings live on every call, so configuration changes (including test
overrides) take effect immediately.

Supported URL shapes
---------------------

The factory produces three shapes, selected purely by configuration (see
:doc:`configuration` for the settings table):

.. code-block:: text

   # Default (no DELIVERY_URL)
   https://imagedelivery.net/<account_hash>/<image_id>/<variant>

   # Native custom domain
   https://<domain>/cdn-cgi/imagedelivery/<account_hash>/<image_id>/<variant>

   # Worker reverse-proxy
   https://<domain>/<image_id>/<variant>

Building URLs
-------------

.. code-block:: python

   from django_cloudflareimages_toolkit import image_url_factory

   # Honors the configured DELIVERY_URL shape.
   image_url_factory.build_url("abc123")                 # default variant: "public"
   image_url_factory.build_url("abc123", "thumbnail")
   image_url_factory.build_url("abc123", "public", account_hash="override-hash")

Rewriting Cloudflare URLs
-------------------------

Cloudflare always returns variant URLs on ``imagedelivery.net``. ``rewrite_url``
converts such a URL into the configured shape, preserving any query string (for
example signed-URL parameters). It is a no-op when no ``DELIVERY_URL`` is
configured or when the URL is not a shared-domain delivery URL.

.. code-block:: python

   stored = "https://imagedelivery.net/HASH/abc123/public"
   image_url_factory.rewrite_url(stored)
   # With DELIVERY_URL='images.example.com':
   #   https://images.example.com/cdn-cgi/imagedelivery/HASH/abc123/public

This is exactly what ``CloudflareImage.get_variant_url`` (and therefore
``public_url`` / ``thumbnail_url``) uses internally, so model URL helpers honor
the configured domain automatically.

Inspecting URLs
---------------

.. code-block:: python

   image_url_factory.is_delivery_url(url)     # True for imagedelivery.net OR the configured host
   image_url_factory.extract_image_id(url)    # the image id, or None
   image_url_factory.split_variant(url)       # (base_without_last_segment, last_segment)

The same helpers back the public ``CloudflareImageUtils.is_cloudflare_image_url``,
``CloudflareImageUtils.extract_image_id``, and
``CloudflareImageUtils.validate_image_url`` functions, so they recognize custom
delivery domains too.

Recognition only matches the exact delivery host. For a custom domain configured
with a path prefix (the default ``cdn-cgi/imagedelivery``), a URL must use that
prefix to be treated as a delivery URL — unrelated assets on the same host (for
example ``https://images.example.com/static/logo.png``) are left for the regular
Image Resizing path instead of being rewritten as flexible variants.

.. note::

   ``extract_image_id`` assumes the final path segment is the variant. A
   custom-path image id (one containing ``/``) used *without* a variant — e.g.
   ``build_url("folder/sub/abc", variant="")`` — cannot be distinguished from
   "id + variant" and will not round-trip. Pair custom-path image ids with a
   variant for reliable extraction and validation.

API reference
-------------

.. autoclass:: django_cloudflareimages_toolkit.url_factory.CloudflareImageURLFactory
   :members:
   :undoc-members:
   :show-inheritance:
