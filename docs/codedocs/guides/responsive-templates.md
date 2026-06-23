---
title: "Responsive Templates"
description: "Use the built-in template tags and transformation utilities to render responsive images in Django templates."
---

This guide covers the template layer shipped in `django_cloudflareimages_toolkit/templatetags/cloudflare_images.py`. It is the right fit when you already have delivery URLs and want consistent responsive markup in Django templates without rebuilding `srcset` strings manually.

<Steps>
<Step>
### Load the tag library

```html
{% load cloudflare_images %}
```

</Step>
<Step>
### Start with simple variants

```html
{% if image.public_url %}
  <img src="{% cf_thumbnail image.public_url 200 %}" alt="Thumbnail">
  <img src="{% cf_hero_image image.public_url 1600 700 %}" alt="Hero">
{% endif %}
```

These tags are wrappers over `CloudflareImageVariants.thumbnail()` and `CloudflareImageVariants.hero_image()`.

</Step>
<Step>
### Generate responsive markup

```html
{% if image.public_url %}
  <img
    src="{% cf_responsive_image image.public_url 800 %}"
    srcset="{% cf_srcset image.public_url '320,640,1024,1600' %}"
    sizes="(max-width: 768px) 100vw, 800px"
    alt="Catalog image"
  >
{% endif %}
```

</Step>
<Step>
### Use the higher-level inclusion tags

```html
{% cf_responsive_img image.public_url "Catalog image" "catalog-image" "320,640,1024" 85 "max-width: 768px:100vw,default:800" %}

{% cf_picture image.public_url "Catalog image" "catalog-image" 400 768 1400 %}
```

`cf_responsive_img` builds `srcset`, a fallback `src`, and a `sizes` string. `cf_picture` builds mobile, tablet, desktop, and fallback sources from the predefined variant helpers.

</Step>
</Steps>

Complete example:

```html
{% load cloudflare_images %}

<article class="product-card">
  <h2>{{ product.name }}</h2>
  {% if product.image %}
    {% with base_url=product.image.get_url %}
      <a href="{% cf_image_transform base_url width=1200 height=1200 fit='contain' %}">
        {% cf_picture base_url product.name "product-card__image" 320 768 1280 %}
      </a>
    {% endwith %}
  {% endif %}
</article>
```

Because the tags call the same transformation helpers documented elsewhere, you can use Python and template code interchangeably: prototype a URL in Python, then move the same option set into template tags once it is stable.

This works especially well with `CloudflareImageFieldValue`, because the field wrapper gives you a clean starting URL while the tags handle the responsive permutations:

```html
{% load cloudflare_images %}

{% if product.image and product.image.get_url %}
  <section class="gallery-item">
    <img
      src="{% cf_responsive_image product.image.get_url 900 %}"
      srcset="{% cf_srcset product.image.get_url '320,640,900,1280' 82 %}"
      sizes="{% cf_sizes 'max-width: 640px:100vw,max-width: 1200px:50vw,default:900' %}"
      alt="{{ product.name }}"
    >
  </section>
{% endif %}
```

Two practical notes from the source code matter here. First, `cf_sizes` strips `px` and `vw` from the width tokens before converting them to integers, so it is best suited to simple numeric breakpoint values rather than arbitrary CSS expressions. Second, the inclusion tags expect template files such as `cloudflare_images/picture_element.html`; if you want the packaged Python helpers without that template contract, stick to the simple tags and render the HTML yourself.
