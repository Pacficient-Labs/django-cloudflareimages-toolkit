"""
Example usage of the CloudflareImageField.

This example demonstrates how to use the newly implemented CloudflareImageField
in a Django model and how it integrates with the existing CloudflareImage model.
"""

from django import forms
from django.db import models

from django_cloudflareimages_toolkit.fields import CloudflareImageField


class Profile(models.Model):
    """Example user profile model using CloudflareImageField."""

    name = models.CharField(max_length=100)
    email = models.EmailField()

    # Simple CloudflareImageField usage
    avatar = CloudflareImageField(
        blank=True,
        null=True,
        help_text="Profile avatar image"
    )

    def __str__(self):
        return self.name


class Product(models.Model):
    """Example product model with advanced CloudflareImageField configuration."""

    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    # Advanced CloudflareImageField with custom options
    image = CloudflareImageField(
        variants=['thumbnail', 'large', 'hero'],
        metadata={'category': 'product'},
        require_signed_urls=False,
        max_file_size=5 * 1024 * 1024,  # 5MB
        allowed_formats=['jpeg', 'png', 'webp'],
        help_text="Product image (JPEG, PNG, or WebP, max 5MB)"
    )

    def __str__(self):
        return self.name


# Example usage in views
def example_usage():
    """Example of how to use the CloudflareImageField in practice."""

    # Create a profile
    profile = Profile.objects.create(
        name="John Doe",
        email="john@example.com",
        # This gets converted to CloudflareImageFieldValue
        avatar="cloudflare-image-id-123"
    )

    # Access the image field
    if profile.avatar:
        print(f"Avatar URL: {profile.avatar.get_url()}")
        print(f"Avatar thumbnail: {profile.avatar.get_url('thumbnail')}")
        print(f"Image ID: {profile.avatar.cloudflare_id}")
        print(f"File size: {profile.avatar.file_size}")
        print(f"Filename: {profile.avatar.filename}")
        print(f"Is ready: {profile.avatar.is_ready}")

    # Create a product with metadata
    product = Product.objects.create(
        name="Awesome Widget",
        description="The best widget you'll ever use",
        price=29.99,
        image="cloudflare-image-id-456"
    )

    # Access product image with variants
    if product.image:
        print(f"Product image URL: {product.image.get_url()}")
        print(f"Thumbnail: {product.image.get_url('thumbnail')}")
        print(f"Large image: {product.image.get_url('large')}")
        print(f"Hero image: {product.image.get_url('hero')}")

        # Get metadata
        metadata = product.image.get_metadata()
        print(f"Image metadata: {metadata}")

        # Update metadata
        product.image.update_metadata({'updated': True, 'featured': True})


# Example Django form usage


class ProfileForm(forms.ModelForm):
    """Example form using CloudflareImageField."""

    class Meta:
        model = Profile
        fields = ['name', 'email', 'avatar']

    # The CloudflareImageField automatically provides a widget
    # that handles file uploads and stores the Cloudflare image ID


class ProductForm(forms.ModelForm):
    """Example product form with custom widget options."""

    class Meta:
        model = Product
        fields = ['name', 'description', 'price', 'image']

    # You can customize the widget if needed
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The widget is automatically configured based on field options
        # but you can override it if needed


# Example template usage
TEMPLATE_EXAMPLE = """
<!-- In your Django template -->
<div class="profile">
    <h2>{{ profile.name }}</h2>
    <p>{{ profile.email }}</p>

    {% if profile.avatar %}
        <img src="{{ profile.avatar.get_url }}" alt="Avatar" class="avatar">
        <!-- Or with a specific variant -->
        <img src="{{ profile.avatar.get_url:'thumbnail' }}" alt="Avatar Thumbnail">
    {% else %}
        <img src="{% static 'images/default-avatar.png' %}" alt="Default Avatar">
    {% endif %}
</div>

<div class="product">
    <h3>{{ product.name }}</h3>
    <p>{{ product.description }}</p>
    <p>${{ product.price }}</p>

    {% if product.image %}
        <!-- Hero image -->
        <img src="{{ product.image.get_url:'hero' }}" alt="{{ product.name }}" class="hero-image">

        <!-- Thumbnail gallery -->
        <div class="thumbnails">
            <img src="{{ product.image.get_url:'thumbnail' }}" alt="Thumbnail">
        </div>

        <!-- Image info -->
        <div class="image-info">
            <p>File size: {{ product.image.file_size|filesizeformat }}</p>
            <p>Filename: {{ product.image.filename }}</p>
            {% if product.image.is_ready %}
                <span class="status ready">Ready</span>
            {% else %}
                <span class="status processing">Processing...</span>
            {% endif %}
        </div>
    {% endif %}
</div>
"""

if __name__ == "__main__":
    print("CloudflareImageField Example Usage")
    print("==================================")
    print()
    print("This example shows how to use the CloudflareImageField in your Django models.")
    print("The field provides a clean, Django-idiomatic way to work with Cloudflare Images.")
    print()
    print("Key features:")
    print("- Stores only the Cloudflare image ID in the database")
    print("- Provides easy access to image URLs and variants")
    print("- Integrates with the existing CloudflareImage model")
    print("- Supports custom metadata and configuration")
    print("- Includes form widgets for easy uploads")
    print("- Works seamlessly in Django templates")
