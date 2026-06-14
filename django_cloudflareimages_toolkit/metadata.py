"""
Programmatic metadata generation for Cloudflare Images uploads.

This module provides :class:`ImageMetadataFactory`, a small extension point that
lets a deployment register a server-side "service" which builds the metadata for
each direct upload (for example: tenant id, request context, timestamps), rather
than relying only on the static ``CLOUDFLARE_IMAGES['DEFAULT_METADATA']`` dict.

Configure it via ``CLOUDFLARE_IMAGES['METADATA_FACTORY']`` as a dotted import
path to a subclass, a class object, an instance, or any plain callable. The
factory receives the already-resolved metadata (``DEFAULT_METADATA`` merged with
the per-request metadata) plus upload context, and returns the final metadata
dict that is sent to Cloudflare and persisted locally.

Merge precedence (lowest to highest):

    DEFAULT_METADATA  <  per-request metadata  <  factory output

Because the factory runs as trusted server-side code it has the final say and
may therefore both augment and override client-supplied keys.
"""

from typing import Any


class ImageMetadataFactory:
    """
    Base class for programmatically generating upload metadata.

    Subclass and override :meth:`get_metadata`. Instances are callable, so the
    service layer can treat a factory instance and a plain callable uniformly.

    Example::

        from django_cloudflareimages_toolkit.metadata import ImageMetadataFactory

        class TenantMetadataFactory(ImageMetadataFactory):
            def get_metadata(self, *, metadata, user=None, **context):
                if user is not None:
                    metadata["uploaded_by"] = str(user.pk)
                metadata["source"] = "web"
                return metadata

        # settings.py
        CLOUDFLARE_IMAGES = {
            # ...
            "METADATA_FACTORY": "myapp.factories.TenantMetadataFactory",
        }
    """

    def get_metadata(
        self,
        *,
        metadata: dict[str, Any],
        user: Any = None,
        custom_id: str | None = None,
        creator: str | None = None,
        **context: Any,
    ) -> dict[str, Any]:
        """
        Return the final metadata dict for an upload.

        Args:
            metadata: The resolved metadata so far (``DEFAULT_METADATA`` merged
                with the per-request metadata).
            user: The Django user associated with the upload, if any.
            custom_id: The custom Cloudflare image ID, if provided.
            creator: The resolved Cloudflare ``creator`` value, if any.
            **context: Forward-compatible additional context.

        Returns:
            The metadata dict to send to Cloudflare. The base implementation
            returns ``metadata`` unchanged.
        """
        return metadata

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        return self.get_metadata(**kwargs)
