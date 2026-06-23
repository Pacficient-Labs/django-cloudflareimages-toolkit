# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release notes are also published on
[GitHub Releases](https://github.com/Pacficient-Labs/django-cloudflareimages-toolkit/releases).

## [1.1.1] - 2026-06-23

### Fixed

- **Migration index names.** Migrations `0001`/`0003` shipped `Meta.indexes`
  names that were 31 characters — one over Django's 30-char `models.E034` limit —
  and never matched the names a newer Django computes for the models, so
  `makemigrations` repeatedly tried to write a spurious `RenameIndex` migration
  into the installed package (site-packages). The model `Meta` index names are
  now pinned to short, valid identifiers, and a new migration
  `0006_pin_index_names` renames the historical indexes in place so existing and
  fresh databases converge on the same names. Verified: `makemigrations --check`
  reports no changes and all 216 tests pass. (No `0002` was ever dropped from the
  history — the migration graph is linear and additive — so a stray leftover
  migration was ruled out as the cause.)

### Documentation

- **Full documentation audit against the code.** Removed settings that don't
  exist (`DEFAULT_VARIANT`, `UPLOAD_TIMEOUT`, `CLEANUP_EXPIRED_HOURS`,
  `ALLOWED_FORMATS`); corrected the webhook URL to include the `api/` segment;
  fixed the `CloudflareImageTransform` examples (it takes a `base_url` and ends
  in `.build()`; there is no `.draw()`/`.url()`); corrected the
  `REQUIRE_SIGNED_URLS` default (`True`) and the `cleanup_expired_images --days`
  default (`7`); flagged the `cf_responsive_img` / `cf_picture` /
  `cf_upload_form` / `cf_image_gallery` inclusion tags as requiring
  caller-supplied templates (the package does not ship them); fixed broken
  `usage`/`api` snippets (the `delete_image` signature, the read-only `is_ready`
  property, `__str__` output, and template-tag call syntax); refreshed `llms.txt`
  (version, models, commands); and corrected GitHub org references. No code
  behavior changed by the docs pass.

### Changed

- **Image usage registry follow-ups (from Codex review on #19).**
  - `ImageUsage` gains a `source` column (`"auto"` / `"manual"`); manual rows
    survive `reconcile_image_usage` regardless of their `field_name`, so callers
    are free to use any label with
    `register_usage(obj, cf_id, field_name="hero")`.
  - `CloudflareImage` gains a `last_referenced_at` column updated each time a
    reference is recorded; `cleanup_expired_images --delete-orphans` now bases
    `--orphan-days` retention on time-since-unused rather than upload time. A
    `null` value falls back to `created_at` for legacy data.
  - `reconcile_image_usage --dry-run` now reports counts from the
    undiscovered-field and dangling-owner pruning passes (previously skipped
    entirely), restoring the safety guarantee of the flag.
  - The lookup route `GET /images/by-cloudflare-id/<cloudflare_id>/` now accepts
    path-style Cloudflare custom IDs (e.g. `products/123/hero`).
  - `?metadata__<key>=...` filters on the list endpoint reject reserved
    JSONField lookup names (`contains`, `has_key`, …) so a stray query param
    can't 500 the view on SQLite.
  - The `ImageUsage` admin denies deletion (`has_delete_permission = False` and
    the bulk `delete_selected` action is dropped) so staff can't silently make
    referenced images look orphaned.
  - **P1 follow-up:** legacy `CloudflareImage` rows that already have
    `ImageUsage` references are backfilled with `last_referenced_at = now()` by
    a one-time data migration, so a long-lived image whose final reference is
    removed immediately after upgrade is not eligible for orphan cleanup.
    The clock is also bumped whenever an `ImageUsage` row is deleted (any
    path) and when `record_usage` reassigns an existing row to a new image, so
    retention correctly tracks the moment a reference disappears.
  - The main reconcile loop now honours `source="manual"` (skipping manual rows
    in both the stale-delete pass and the upsert), so a manual row whose
    `field_name` collides with a tracked field is no longer wiped or
    re-classified as `source="auto"`.
  - **Second-review follow-ups:** `register_usage` raises `ValueError` if
    `field_name` collides with a tracked `CloudflareImageField` (they would share
    a uniqueness slot). `reconcile_image_usage` now computes a deduplicated set of
    rows to delete, so `--dry-run` and the real run report identical counts even
    when a row is both stale and dangling. `?metadata__<key>=...` filters accept
    non-identifier JSON keys (hyphens, dots, nested) and return **400** for a
    reserved lookup operator instead of silently dropping the filter or 500-ing.
    The `0005` data migration backfills `last_referenced_at` for already-referenced
    images but deliberately does **not** infer `source` for pre-existing rows
    (a legacy auto row for a removed field is indistinguishable from a legacy
    custom-label manual row); `source` is authoritative only for rows created by
    `register_usage` from this release on. If you used a custom manual label on a
    pre-release dev build, re-run those `register_usage` calls after upgrading.

### Added

- **Configurable image delivery URL.** New `CLOUDFLARE_IMAGES` keys let site
  admins serve images from an alternate domain instead of the shared
  `imagedelivery.net`: `DELIVERY_URL` (the alternate host or base URL),
  `DELIVERY_PATH_PREFIX` (default `cdn-cgi/imagedelivery`; set to `''` for a
  Worker proxy), and `DELIVERY_INCLUDE_ACCOUNT_HASH` (default `True`; set to
  `False` for a Worker proxy). When `DELIVERY_URL` is unset the shared domain is
  used and behavior is unchanged.
- **`CloudflareImageURLFactory` and the `image_url_factory` singleton.** A new
  single source of truth for building, recognizing, extracting from, and
  rewriting Cloudflare Images delivery URLs. Both are exported from the package
  root. See the new `docs/url_factory.rst` guide.
- **Image Usage Registry (SSOT).** A new `ImageUsage` model and registry track
  *which content references each image*, complementing `CloudflareImage` (what
  has been uploaded). Every `CloudflareImageField` across installed apps is
  auto-discovered, and usage rows are kept in sync via signals on save/delete.
  Reverse lookups become trivial: `image.usages.all()`, orphaned images
  (`CloudflareImage.objects.filter(usages__isnull=True)`), and unregistered
  references (`ImageUsage.objects.filter(image__isnull=True)`).
- **Manual registration API.** `register_usage(obj, cloudflare_id,
  field_name="manual")` and `unregister_usage(obj, field_name="manual")` record
  references the toolkit cannot discover automatically. Also exported:
  `ImageUsage` and `get_models_with_image_fields`.
- **Admin gallery + usage surfacing.** The `CloudflareImage` changelist gains a
  thumbnail **gallery view** (toggle to table) with status/orphan/usage badges, a
  "Used by" inline linking to referencing objects, an **Orphaned** filter, and
  usage/orphan/unregistered counts on the stats dashboard. A new `ImageUsage`
  admin adds an **Unregistered** filter.
- **REST API additions.** Look up by Cloudflare ID
  (`/images/by-cloudflare-id/{cloudflare_id}/`), list a single image's references
  (`/images/{id}/usages/`), list orphans (`/images/orphans/`), browse all usages
  (`/usages/`), plus search/filter params (`filename`, `creator`, `orphaned`,
  `search`, `ordering`, `metadata__<key>`). Deletes are now **usage-aware**:
  `DELETE /images/{id}/` returns HTTP 409 when the image is still referenced
  unless `?force=true`, and a new `POST /images/bulk_delete/` removes many at once
  (from Cloudflare and the database).
- **Management commands.** New `reconcile_image_usage` rebuilds the registry from
  host models (the fix for signal-bypassing bulk operations) and reports
  orphans/unregistered references. `cleanup_expired_images` gains opt-in
  `--delete-orphans` / `--orphan-days N` flags.

### Changed

- **Delivery URL construction is centralized through the URL factory.**
  `CloudflareImage.get_variant_url` (and therefore `public_url` / `thumbnail_url`),
  the `CloudflareImageField` URL fallback, and the `CloudflareImageUtils` helpers
  (`is_cloudflare_image_url`, `extract_image_id`, `validate_image_url`) plus
  `CloudflareImageTransform` now honor a configured custom delivery domain and
  recognize its URLs. Stored Cloudflare variants (always returned on
  `imagedelivery.net`) are rewritten to the configured domain on read, preserving
  any query string such as signed-URL parameters.

### Fixed

- `CloudflareImageViewSet` list filtering no longer applies the optional boolean
  filters (`has_variants`, `require_signed_urls`) unless they are actually present
  in the request, fixing spuriously empty results.

## [1.1.0] - 2026-06-14

### Added

- **Configurable upload defaults via Django settings.** New
  `CLOUDFLARE_IMAGES` keys `DEFAULT_METADATA` (a dict merged underneath any
  per-request metadata) and `DEFAULT_CREATOR` (a default Cloudflare `creator`
  value). Per-request values continue to take precedence. These complement the
  existing `REQUIRE_SIGNED_URLS` and `DEFAULT_EXPIRY_MINUTES` defaults.
- **Cloudflare `creator` support, end to end.** `create_direct_upload_url`
  (and `get_direct_upload_url`) accept a `creator` argument, the upload-URL API
  endpoint accepts a `creator` field, the value is sent to Cloudflare's
  `/images/v2/direct_upload` call (multipart form), and a new indexed
  `CloudflareImage.creator` field persists it so records are queryable from
  Django.
- **`ImageMetadataFactory` extension point.** Register a server-side factory via
  `CLOUDFLARE_IMAGES['METADATA_FACTORY']` (dotted path, class, instance, or
  callable) to build upload metadata programmatically. It receives the resolved
  metadata plus upload context and has the final say. Merge precedence:
  `DEFAULT_METADATA` < per-request metadata < factory output.
- **`CloudflareImage.objects.register_uploaded(cloudflare_id, user=None,
  expected_creator=None)`.** A safe, first-class way to register a
  client-supplied `cloudflare_id`: it fetches the image from Cloudflare, confirms
  it exists and is no longer a draft, then creates/returns the local record
  populated with status, variants, metadata, and creator. Raises the typed
  `ImageNotFoundError` (missing) or new `ImageNotReadyError` (still a draft)
  instead of silently trusting input. Pass `expected_creator` (e.g. the
  uploader's id) to require the Cloudflare `creator` to match before any local
  row is created, raising `ImageOwnershipError` otherwise — this stops a caller
  registering another user's completed image by submitting an arbitrary id.
  `ImageOwnershipError` is also raised when the `cloudflare_id` is already
  tracked locally for a different user, so the method never returns another
  user's record.
- New `ImageNotReadyError` and `ImageOwnershipError` exceptions, exported from
  the package root alongside `ImageMetadataFactory`.

### Changed

- `update_from_cloudflare_response` now also maps Cloudflare's `creator` and
  `filename`, accepts `meta` as an alias for `metadata`, and parses Cloudflare's
  `uploaded` timestamp instead of stamping the current time (so registering or
  re-syncing a previously uploaded image keeps the real upload time and the
  `uploaded_after`/`uploaded_before` filters stay correct).
- `get_image` now raises `ImageNotFoundError` (a `CloudflareImagesError`
  subclass) on a Cloudflare 404, so existing `except CloudflareImagesError`
  handlers keep working.
- The `creator` column is `max_length=255` and indexed. The service rejects an
  over-length `creator` before the Cloudflare request (so an upload is never
  left untracked), and truncates longer `creator` values returned for
  externally-created images on registration.

### Fixed

- `CreateUploadURLView` no longer risks an unexpected-keyword `TypeError` when a
  client supplies `filename`; it is now extracted before delegating to the
  service.
- Non-dict `metadata` is rejected with a clean 400 (serializer) / typed
  `CloudflareImagesError` (service) instead of a 500 from the defaults merge.
- `register_uploaded` mirrors Cloudflare's `meta` into the queryable `metadata`
  field, so registered rows are filterable via `metadata__...` as documented.
- The upload endpoint's `creator` field accepts an empty string (`allow_blank`),
  so an API caller can send `""` to force an untagged upload that bypasses
  `DEFAULT_CREATOR` (previously a `400`).
- `register_uploaded` refreshes a pre-existing row's `require_signed_urls` from
  Cloudflare (`get_or_create` ignores `defaults` for existing rows), so the
  signed-URL stat/filter no longer goes stale on re-registration.
- `register_uploaded` rejects a `cloudflare_id` longer than the column (255)
  with a typed `CloudflareImagesError` before the remote lookup, instead of a
  database error after the Cloudflare call succeeds.
- Migration `0002` backfills the new `creator` column with an explicit empty
  string so existing rows upgrade cleanly on every database backend.

### Security

- Documented that `get_or_create(cloudflare_id=<client value>)` is unsafe and
  pointed consumers at `register_uploaded`, which validates against Cloudflare
  before persisting.

[1.1.1]: https://github.com/Pacficient-Labs/django-cloudflareimages-toolkit/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/Pacficient-Labs/django-cloudflareimages-toolkit/compare/v1.0.14...v1.1.0
