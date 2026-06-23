"""
Django form widgets for Cloudflare Images integration.

This module provides a custom form widget for handling image uploads with
Cloudflare Images. The upload behaviour -- HTML structure, JavaScript, and
styling -- lives in the package's template and static assets, NOT inline in
Python:

  * template: ``templates/django_cloudflareimages_toolkit/widgets/cloudflare_image_widget.html``
  * script:   ``static/django_cloudflareimages_toolkit/js/cloudflare_image_widget.js``
  * styles:   ``static/django_cloudflareimages_toolkit/css/cloudflare_image_widget.css``

The widget's only responsibility here is to assemble the per-field ``config``
payload **once** (:meth:`CloudflareImageWidget.get_context` /
:meth:`_build_config`) and hand it to the template (and to an equivalent
minimal fallback), so the markup and the script can never drift apart.

The upload endpoint is resolved from its named route
(``cloudflare_images:create-upload-url``) rather than hardcoded, so the single
source of truth for that URL is its ``path()`` definition (see issue #22).
"""

from typing import Any

from django import forms
from django.forms.renderers import get_default_renderer
from django.template import TemplateDoesNotExist
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html, json_script
from django.utils.safestring import SafeText, mark_safe

from .constants import DEFAULT_ALLOWED_FORMATS

# Named route (see ``urls.py``: ``app_name = "cloudflare_images"``) that issues a
# direct creator upload URL. Resolved at render time so the widget always posts
# to the real endpoint and remounting/renaming the URL propagates automatically.
UPLOAD_URL_NAME = "cloudflare_images:create-upload-url"


class CloudflareImageWidget(forms.TextInput):
    """
    A widget for handling Cloudflare image uploads.

    This widget renders a hidden input (which stores the Cloudflare image id)
    alongside a file input that drives the direct-upload flow implemented in the
    accompanying static JavaScript. The behaviour is loaded via the widget's
    :class:`Media`; this class only builds the configuration the template and
    script consume.
    """

    template_name = (
        "django_cloudflareimages_toolkit/widgets/cloudflare_image_widget.html"
    )

    def __init__(
        self,
        variants: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        require_signed_urls: bool = False,
        max_file_size: int | None = None,
        allowed_formats: list[str] | None = None,
        attrs: dict[str, Any] | None = None,
    ):
        """
        Initialize the widget.

        Args:
            variants: List of image variants to create
            metadata: Default metadata for uploads
            require_signed_urls: Whether to require signed URLs
            max_file_size: Maximum file size in bytes
            allowed_formats: List of allowed image formats
            attrs: Additional HTML attributes
        """
        self.variants = variants or []
        self.metadata = metadata or {}
        self.require_signed_urls = require_signed_urls
        self.max_file_size = max_file_size
        # Copy the shared default so the constant is never mutated through a
        # widget instance (and instances don't accidentally share one list).
        self.allowed_formats = allowed_formats or list(DEFAULT_ALLOWED_FORMATS)

        default_attrs = {"type": "hidden", "class": "cloudflare-image-field"}
        if attrs:
            default_attrs.update(attrs)

        super().__init__(attrs=default_attrs)

    def format_value(self, value):
        """Format the field value for display."""
        if value is None:
            return ""
        return str(value)

    def _resolve_upload_endpoint(self) -> str:
        """Resolve the upload endpoint from its named route (SSOT).

        Returns an empty string when the API URLs aren't mounted
        (``NoReverseMatch``); the JS then surfaces a clear "endpoint not
        configured" error rather than POSTing to a wrong/dead path.
        """
        try:
            return reverse(UPLOAD_URL_NAME)
        except NoReverseMatch:
            return ""

    def _build_config(self) -> dict[str, Any]:
        """Assemble the single ``config`` payload shared by template and JS.

        This is the one place the widget's runtime configuration is built, so
        :meth:`render` and :meth:`_render_fallback` can never serialize a
        different payload.
        """
        return {
            "variants": self.variants,
            "metadata": self.metadata,
            "require_signed_urls": self.require_signed_urls,
            "max_file_size": self.max_file_size,
            "allowed_formats": self.allowed_formats,
            "api_endpoint": self._resolve_upload_endpoint(),
        }

    def get_context(
        self, name: str, value: Any, attrs: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Build the template context, assembling the config payload once."""
        context = super().get_context(name, value, attrs)
        widget = context["widget"]

        # The form supplies an ``id`` for the hidden input; fall back to Django's
        # conventional ``id_<name>`` so the derived element ids are stable.
        field_id = widget["attrs"].get("id") or f"id_{name}"
        config = self._build_config()

        widget.update(
            {
                "field_id": field_id,
                "upload_id": f"{field_id}_upload",
                "preview_id": f"{field_id}_preview",
                "progress_id": f"{field_id}_progress",
                "config_id": f"{field_id}_config",
                # The config is emitted to the page exclusively via Django's
                # ``json_script`` (in the template and the fallback), which
                # escapes ``<``/``>``/``&`` so metadata can't break out of the
                # <script> block. We intentionally do NOT expose a
                # ``mark_safe(json.dumps(...))`` string here: that pattern does
                # not escape those characters and is an XSS footgun if a template
                # drops it into a <script> tag.
                "config": config,
                # Individual values exposed for template convenience.
                "variants": self.variants,
                "metadata": self.metadata,
                "require_signed_urls": self.require_signed_urls,
                "max_file_size": self.max_file_size,
                "allowed_formats": self.allowed_formats,
                "api_endpoint": config["api_endpoint"],
            }
        )
        return context

    def render(
        self, name: str, value: Any, attrs: dict[str, Any] | None = None, renderer=None
    ) -> SafeText:
        """
        Render the widget HTML from the template.

        Falls back to a minimal, equivalent markup block only if the package's
        templates aren't reachable on the loader path.
        """
        if renderer is None:
            renderer = get_default_renderer()

        context = self.get_context(name, value, attrs)
        try:
            return mark_safe(renderer.render(self.template_name, context))
        except TemplateDoesNotExist:
            return self._render_fallback(context)

    def _render_fallback(self, context: dict[str, Any]) -> SafeText:
        """
        Minimal fallback used only when the widget template can't be loaded.

        It renders the hidden field, the file input, and the same json_script
        config block, then relies on the static JS (declared in :class:`Media`)
        for behaviour. It deliberately does NOT re-implement the upload flow or
        inline any JavaScript/CSS -- that lives in the static assets, defined
        once.
        """
        widget = context["widget"]
        # json_script safely serializes + HTML-escapes the config into a
        # <script type="application/json"> block the static JS reads, exactly as
        # the template's ``|json_script`` filter does.
        config_script = json_script(widget["config"], widget["config_id"])

        return format_html(
            '<div class="cloudflare-image-upload-container" '
            'data-cfimg-field="{field_id}">'
            '<input type="hidden" name="{name}" id="{field_id}" value="{value}" '
            'class="cloudflare-image-field">'
            '<input type="file" id="{upload_id}" accept="image/*" '
            'class="cloudflare-image-upload">'
            '<div id="{preview_id}" class="cloudflare-image-preview"></div>'
            '<div id="{progress_id}" class="cloudflare-image-progress" '
            'style="display: none;">'
            '<div class="progress-bar"></div>'
            '<span class="progress-text">Uploading…</span>'
            "</div>{config_script}</div>",
            field_id=widget["field_id"],
            name=widget["name"],
            value=widget["value"],
            upload_id=widget["upload_id"],
            preview_id=widget["preview_id"],
            progress_id=widget["progress_id"],
            config_script=config_script,
        )

    class Media:
        """Define media files for the widget."""

        css = {
            "all": ("django_cloudflareimages_toolkit/css/cloudflare_image_widget.css",)
        }
        js = ("django_cloudflareimages_toolkit/js/cloudflare_image_widget.js",)
