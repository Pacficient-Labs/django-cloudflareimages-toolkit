/**
 * Cloudflare Images upload widget.
 *
 * Drives the direct-creator upload flow for CloudflareImageWidget. This is the
 * single home for the upload behaviour -- it is NOT duplicated inline in
 * widgets.py. Per-field configuration (variants, metadata, limits, and the
 * upload endpoint, which is resolved server-side from the named route
 * cloudflare_images:create-upload-url) is read from a json_script block emitted
 * next to the widget markup, so this script and the template share one config
 * and can never drift.
 *
 * Flow: select file -> validate -> POST config.api_endpoint to get a one-time
 * Cloudflare upload URL -> POST the file to Cloudflare -> store the resulting
 * image id in the hidden input.
 */
(function () {
  "use strict";

  function getCsrfToken() {
    const cookies = document.cookie ? document.cookie.split(";") : [];
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split("=");
      if (name === "csrftoken") {
        return decodeURIComponent(value);
      }
    }
    return "";
  }

  function readConfig(fieldId) {
    // Configuration is emitted once via Django's json_script (see the widget
    // template), keyed as "<fieldId>_config". Parsing it here is the single
    // source of the widget's runtime config.
    const el = document.getElementById(fieldId + "_config");
    if (!el) {
      return null;
    }
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      console.error("Cloudflare widget: invalid config JSON", e);
      return null;
    }
  }

  function validateFile(file, config) {
    if (config.max_file_size && file.size > config.max_file_size) {
      alert("File size exceeds the maximum allowed size.");
      return false;
    }
    const formats = config.allowed_formats || [];
    const fileType = (file.type.split("/")[1] || "").toLowerCase();
    if (formats.length && formats.indexOf(fileType) === -1) {
      alert("File format not allowed.");
      return false;
    }
    return true;
  }

  function showPreview(previewEl, url) {
    if (!previewEl) {
      return;
    }
    previewEl.innerHTML = "";
    if (!url) {
      return;
    }
    const img = document.createElement("img");
    img.src = url;
    img.alt = "Image preview";
    previewEl.appendChild(img);
  }

  async function uploadFile(file, ctx) {
    const config = ctx.config;
    if (!config.api_endpoint) {
      // The named route could not be resolved server-side (API URLs not
      // mounted). Fail loudly instead of POSTing to a wrong/dead path.
      alert("Upload endpoint is not configured.");
      return;
    }

    try {
      if (ctx.progressEl) {
        ctx.progressEl.style.display = "block";
      }
      if (ctx.previewEl) {
        ctx.previewEl.innerHTML = "";
      }

      const urlResponse = await fetch(config.api_endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
        body: JSON.stringify({
          metadata: config.metadata,
          require_signed_urls: config.require_signed_urls,
        }),
      });
      if (!urlResponse.ok) {
        throw new Error("Failed to get upload URL");
      }
      const uploadData = await urlResponse.json();
      const uploadURL = uploadData.upload_url || uploadData.uploadURL;

      const formData = new FormData();
      formData.append("file", file);
      const uploadResponse = await fetch(uploadURL, {
        method: "POST",
        body: formData,
      });
      if (!uploadResponse.ok) {
        throw new Error("Upload failed");
      }
      const result = await uploadResponse.json();

      // Prefer Cloudflare's echoed id; fall back to the id our backend issued.
      const cfId = (result.result && result.result.id) || uploadData.cloudflare_id;
      ctx.hiddenInput.value = cfId || "";

      const variants = (result.result && result.result.variants) || [];
      showPreview(ctx.previewEl, variants.length ? variants[0] : null);

      if (ctx.progressEl) {
        ctx.progressEl.style.display = "none";
      }
    } catch (error) {
      console.error("Cloudflare upload error:", error);
      alert("Upload failed: " + error.message);
      if (ctx.progressEl) {
        ctx.progressEl.style.display = "none";
      }
    }
  }

  function initContainer(container) {
    const fieldId = container.getAttribute("data-cfimg-field");
    if (!fieldId) {
      return;
    }
    const config = readConfig(fieldId) || {};
    const hiddenInput = document.getElementById(fieldId);
    const uploadInput = document.getElementById(fieldId + "_upload");
    const previewEl = document.getElementById(fieldId + "_preview");
    const progressEl = document.getElementById(fieldId + "_progress");
    if (!uploadInput || !hiddenInput) {
      return;
    }

    // Show an existing value's id is already stored; nothing to preview without
    // a delivery URL, so we only wire the change handler.
    uploadInput.addEventListener("change", function (event) {
      const file = event.target.files[0];
      if (!file || !validateFile(file, config)) {
        return;
      }
      uploadFile(file, { config, hiddenInput, previewEl, progressEl });
    });
  }

  function init() {
    const containers = document.querySelectorAll(
      ".cloudflare-image-upload-container[data-cfimg-field]"
    );
    containers.forEach(initContainer);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
