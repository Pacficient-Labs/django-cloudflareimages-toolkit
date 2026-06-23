"""
Image usage registry — the source of truth for *where* Cloudflare images are used.

The toolkit already tracks *what* has been uploaded (``CloudflareImage``). This
module adds the missing half: *which content references which image*. It has two
layers:

* a **field registry** (:func:`get_models_with_image_fields`) that auto-discovers
  every :class:`~django_cloudflareimages_toolkit.fields.CloudflareImageField`
  declared on installed models, and
* idempotent **sync helpers** that keep the materialised
  :class:`~django_cloudflareimages_toolkit.models.ImageUsage` index in step with
  those fields, plus a small public API (:func:`register_usage` /
  :func:`unregister_usage`) for references the toolkit cannot discover by itself.

Design notes:

* SSOT — the host field's stored ``cloudflare_id`` is the source of truth for a
  reference; ``ImageUsage`` is a derived index that can always be rebuilt from the
  models with the ``reconcile_image_usage`` management command.
* Determinism — discovery iterates models/fields in a stable sorted order.
* Idempotency — every write goes through ``update_or_create``/``delete`` keyed on
  ``(content_type, object_id, field_name)`` (also enforced by a unique
  constraint), so repeating any operation converges to the same state.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType

# ``field_name`` used for references recorded through the manual API.
MANUAL_FIELD_NAME = "manual"

# Cache of {model_class: [field_name, ...]}. Built lazily; rebuilt on refresh.
_field_cache: dict | None = None


def get_models_with_image_fields(refresh: bool = False) -> dict:
    """Return ``{model_class: [field_name, ...]}`` for every CloudflareImageField.

    This is the single source of truth for where images can live, derived from the
    model definitions themselves so it never drifts from the code. Results are
    cached; pass ``refresh=True`` to rebuild (useful in tests that declare models
    after the app registry is first inspected).
    """
    global _field_cache
    if _field_cache is None or refresh:
        from .fields import CloudflareImageField

        cache: dict = {}
        for model in sorted(django_apps.get_models(), key=lambda m: m._meta.label):
            names = sorted(
                f.name
                for f in model._meta.get_fields()
                if isinstance(f, CloudflareImageField)
            )
            if names:
                cache[model] = names
        _field_cache = cache
    return _field_cache


def get_tracked_field_names(model) -> list:
    """Return the CloudflareImageField names on ``model`` (empty if none)."""
    return get_models_with_image_fields().get(model, [])


def _extract_cloudflare_id(value) -> str | None:
    """Pull a cloudflare_id out of a field value (handles the wrapper or a str)."""
    if value is None:
        return None
    cloudflare_id = getattr(value, "cloudflare_id", None)
    if cloudflare_id:
        return cloudflare_id
    if isinstance(value, str) and value:
        return value
    return None


def _resolve_image(cloudflare_id: str):
    """Return the CloudflareImage for ``cloudflare_id`` if one exists, else None."""
    from .models import CloudflareImage

    return CloudflareImage.objects.filter(cloudflare_id=cloudflare_id).first()


def record_usage(content_type, object_id, field_name: str, cloudflare_id: str):
    """Idempotently upsert one usage row. The single shared write path."""
    from .models import ImageUsage

    usage, _ = ImageUsage.objects.update_or_create(
        content_type=content_type,
        object_id=str(object_id),
        field_name=field_name,
        defaults={
            "cloudflare_id": cloudflare_id,
            "image": _resolve_image(cloudflare_id),
        },
    )
    return usage


def clear_usage(content_type, object_id, field_name: str) -> None:
    """Remove the usage row for a (object, field) if present (idempotent)."""
    from .models import ImageUsage

    ImageUsage.objects.filter(
        content_type=content_type, object_id=str(object_id), field_name=field_name
    ).delete()


def sync_object(instance) -> None:
    """Synchronise usage rows for every tracked field on a single instance."""
    field_names = get_tracked_field_names(type(instance))
    if not field_names:
        return
    content_type = ContentType.objects.get_for_model(type(instance))
    for field_name in field_names:
        cloudflare_id = _extract_cloudflare_id(getattr(instance, field_name, None))
        if cloudflare_id:
            record_usage(content_type, instance.pk, field_name, cloudflare_id)
        else:
            clear_usage(content_type, instance.pk, field_name)


def clear_object(instance) -> None:
    """Remove every usage row attached to a (deleted) instance."""
    from .models import ImageUsage

    content_type = ContentType.objects.get_for_model(type(instance))
    ImageUsage.objects.filter(
        content_type=content_type, object_id=str(instance.pk)
    ).delete()


# --- Public manual-registration API -----------------------------------------


def register_usage(obj, cloudflare_id: str, field_name: str = MANUAL_FIELD_NAME):
    """Manually record that ``obj`` references ``cloudflare_id``.

    Use this for references the toolkit cannot discover automatically — an image
    ID kept in a ``JSONField``, fetched from another service, or derived at
    runtime rather than stored in a ``CloudflareImageField``. Idempotent: calling
    again for the same ``(obj, field_name)`` updates the row in place.

    Args:
        obj: Any saved model instance that "owns" the reference.
        cloudflare_id: The Cloudflare image ID being referenced.
        field_name: A label distinguishing this reference from others on the same
            object (defaults to ``"manual"``).

    Returns:
        The created or updated :class:`~...models.ImageUsage` row.
    """
    content_type = ContentType.objects.get_for_model(type(obj))
    return record_usage(content_type, obj.pk, field_name, cloudflare_id)


def unregister_usage(obj, field_name: str = MANUAL_FIELD_NAME) -> None:
    """Remove a manually-registered usage for ``obj`` (idempotent)."""
    content_type = ContentType.objects.get_for_model(type(obj))
    clear_usage(content_type, obj.pk, field_name)
