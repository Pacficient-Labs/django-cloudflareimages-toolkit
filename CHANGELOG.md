# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release notes are also published on
[GitHub Releases](https://github.com/Pacficient-Labs/django-cloudflareimages-toolkit/releases).

## [1.1.0]

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
- **`CloudflareImage.objects.register_uploaded(cloudflare_id, user=None)`.** A
  safe, first-class way to register a client-supplied `cloudflare_id`: it fetches
  the image from Cloudflare, confirms it exists and is no longer a draft, then
  creates/returns the local record populated with status, variants, metadata,
  and creator. Raises the typed `ImageNotFoundError` (missing) or new
  `ImageNotReadyError` (still a draft) instead of silently trusting input.
- New `ImageNotReadyError` exception, exported from the package root alongside
  `ImageMetadataFactory`.

### Changed

- `update_from_cloudflare_response` now also maps Cloudflare's `creator` and
  `filename`, and accepts `meta` as an alias for `metadata`.
- `get_image` now raises `ImageNotFoundError` (a `CloudflareImagesError`
  subclass) on a Cloudflare 404, so existing `except CloudflareImagesError`
  handlers keep working.

### Fixed

- `CreateUploadURLView` no longer risks an unexpected-keyword `TypeError` when a
  client supplies `filename`; it is now extracted before delegating to the
  service.

### Security

- Documented that `get_or_create(cloudflare_id=<client value>)` is unsafe and
  pointed consumers at `register_uploaded`, which validates against Cloudflare
  before persisting.
