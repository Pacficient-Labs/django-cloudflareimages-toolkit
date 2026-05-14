---
title: "Model Field and Forms"
description: "Attach Cloudflare IDs to your own models with CloudflareImageField and understand the widget behavior."
---

This guide is for applications that want a Django-idiomatic field on their own models while still letting the package track full upload state in `CloudflareImage`. The field stores only the Cloudflare image ID in your model, then exposes a richer wrapper object at runtime.

<Steps>
<Step>
### Define your model

```python
from django.db import models

from django_cloudflareimages_toolkit.fields import CloudflareImageField


class Product(models.Model):
    name = models.CharField(max_length=200)
    image = CloudflareImageField(
        variants=["thumbnail", "hero"],
        metadata={"kind": "product"},
        require_signed_urls=False,
        max_file_size=5 * 1024 * 1024,
        allowed_formats=["jpeg", "png", "webp"],
        blank=True,
        null=True,
    )
```

</Step>
<Step>
### Use the generated wrapper object in application code

```python
product = Product.objects.get(pk=1)

if product.image:
    print(product.image.cloudflare_id)
    print(product.image.get_url("thumbnail"))
    print(product.image.get_metadata())
    print(product.image.is_ready)
```

`CloudflareImageField.to_python()` turns the stored string into `CloudflareImageFieldValue`, and `get_prep_value()` writes only the Cloudflare ID back to the database.

</Step>
<Step>
### Render the field in a ModelForm

```python
from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "image"]
```

`CloudflareImageField.formfield()` automatically supplies `CloudflareImageWidget` with the field configuration you passed to the model field.

</Step>
<Step>
### Override the widget template in real projects

The package exposes `CloudflareImageWidget`, but the source tree does not ship the referenced template file. When template rendering fails, the widget falls back to inline HTML and JavaScript produced by `_render_fallback()`.

```python
from django import forms

from django_cloudflareimages_toolkit.widgets import CloudflareImageWidget


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "image"]
        widgets = {
            "image": CloudflareImageWidget(
                metadata={"kind": "product"},
                allowed_formats=["jpeg", "png", "webp"],
            )
        }
```

</Step>
</Steps>

Runnable view example:

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ProductForm


@login_required
def create_product(request):
    form = ProductForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("product-list")
    return render(request, "products/create.html", {"form": form})
```

<Callout type="warn">The widget fallback JavaScript in `django_cloudflareimages_toolkit/widgets.py` assumes endpoints such as `/cloudflare-images/get-upload-url/` and `/cloudflare-images/image/<id>/thumbnail/`, but the packaged URLs are actually under `/cloudflare-images/api/...`. In production, override the widget template or subclass the widget so the frontend calls your real upload and preview endpoints.</Callout>
