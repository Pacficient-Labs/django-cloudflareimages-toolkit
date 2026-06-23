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
from django.db.utils import DEFAULT_DB_ALIAS

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


def _db(using):
    """Resolve a database alias, defaulting to Django's default DB."""
    return using or DEFAULT_DB_ALIAS


def _content_type_for(model, using=None):
    """Get the ContentType for ``model`` on the targeted database.

    ``ContentType.objects.get_for_model`` caches across databases, so we use
    ``db_manager`` to ensure the row is fetched (and, on first use, created) on
    the database where the related rows actually live.
    """
    return ContentType.objects.db_manager(_db(using)).get_for_model(model)


def _resolve_image(cloudflare_id: str, using=None):
    """Return the CloudflareImage for ``cloudflare_id`` if one exists, else None."""
    from .models import CloudflareImage

    return (
        CloudflareImage.objects.using(_db(using))
        .filter(cloudflare_id=cloudflare_id)
        .first()
    )


def _bump_last_referenced(image_or_pk, using=None) -> None:
    """Mark an image as referenced now.

    Accepts either a ``CloudflareImage`` instance or a bare primary key (the
    latter is used by the ``ImageUsage`` ``post_delete`` receiver where the row
    is gone but its FK pk is still available on ``instance.image_id``).

    Updated via ``.update()`` so this doesn't trigger ``post_save`` (and thus
    won't recurse through the registry's own signals).
    """
    if image_or_pk is None:
        return
    from django.utils import timezone

    from .models import CloudflareImage

    pk = image_or_pk.pk if hasattr(image_or_pk, "pk") else image_or_pk
    CloudflareImage.objects.using(_db(using)).filter(pk=pk).update(
        last_referenced_at=timezone.now()
    )


def record_usage(
    content_type,
    object_id,
    field_name: str,
    cloudflare_id: str,
    source: str = "auto",
    using=None,
):
    """Idempotently upsert one usage row. The single shared write path.

    ``source`` distinguishes auto-discovered rows (``"auto"``) from manual-API
    rows (``"manual"``); ``reconcile_image_usage`` preserves the latter no
    matter what their ``field_name`` is.
    """
    from .models import ImageUsage

    image = _resolve_image(cloudflare_id, using=using)

    # If an existing row for this slot pointed at a different image, that image
    # is losing a reference. Bump its ``last_referenced_at`` so its orphan-
    # retention clock starts from now rather than from the original upload.
    existing_image_id = (
        ImageUsage.objects.using(_db(using))
        .filter(
            content_type=content_type,
            object_id=str(object_id),
            field_name=field_name,
        )
        .values_list("image_id", flat=True)
        .first()
    )
    new_pk = image.pk if image is not None else None
    if existing_image_id is not None and existing_image_id != new_pk:
        _bump_last_referenced(existing_image_id, using=using)

    usage, _ = ImageUsage.objects.using(_db(using)).update_or_create(
        content_type=content_type,
        object_id=str(object_id),
        field_name=field_name,
        defaults={
            "cloudflare_id": cloudflare_id,
            "image": image,
            "source": source,
        },
    )
    _bump_last_referenced(image, using=using)
    return usage


def clear_usage(content_type, object_id, field_name: str, using=None) -> None:
    """Remove the usage row for a (object, field) if present (idempotent)."""
    from .models import ImageUsage

    ImageUsage.objects.using(_db(using)).filter(
        content_type=content_type, object_id=str(object_id), field_name=field_name
    ).delete()


def sync_object(instance, using=None) -> None:
    """Synchronise usage rows for every tracked field on a single instance."""
    field_names = get_tracked_field_names(type(instance))
    if not field_names:
        return
    content_type = _content_type_for(type(instance), using=using)
    for field_name in field_names:
        cloudflare_id = _extract_cloudflare_id(getattr(instance, field_name, None))
        if cloudflare_id:
            record_usage(
                content_type, instance.pk, field_name, cloudflare_id, using=using
            )
        else:
            clear_usage(content_type, instance.pk, field_name, using=using)


def clear_object(instance, using=None) -> None:
    """Remove every usage row attached to a (deleted) instance."""
    from .models import ImageUsage

    content_type = _content_type_for(type(instance), using=using)
    ImageUsage.objects.using(_db(using)).filter(
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
    model = type(obj)
    using = obj._state.db
    content_type = _content_type_for(model, using=using)
    usage = record_usage(
        content_type,
        obj.pk,
        field_name,
        cloudflare_id,
        source="manual",
        using=using,
    )
    # Ensure the owner's deletion clears its usage rows even when the model has
    # no CloudflareImageField (and so was never wired in apps.ready()).
    ensure_delete_cleanup(model)
    return usage


def unregister_usage(obj, field_name: str = MANUAL_FIELD_NAME) -> None:
    """Remove a manually-registered usage for ``obj`` (idempotent)."""
    using = obj._state.db
    content_type = _content_type_for(type(obj), using=using)
    clear_usage(content_type, obj.pk, field_name, using=using)


def ensure_delete_cleanup(model) -> None:
    """Connect post_delete usage cleanup for ``model`` (idempotent).

    Auto-discovered models are wired in ``apps.ready()``; this also covers models
    reachable only through the manual API, so deleting such an owner removes its
    ``ImageUsage`` rows instead of leaking them. The shared ``dispatch_uid`` makes
    this a no-op for models already connected.
    """
    from django.db.models.signals import post_delete

    from . import signals

    post_delete.connect(
        signals.remove_instance_usage,
        sender=model,
        dispatch_uid=f"cfimg_usage_delete_{model._meta.label}",
    )
