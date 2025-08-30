"""
URL configuration for testing django-cloudflareimages-toolkit
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cloudflare-images/', include('django_cloudflareimages_toolkit.urls')),
]
