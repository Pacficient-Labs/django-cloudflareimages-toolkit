"""
Tests for the Django 7.0-ready ``get_actions()`` signature (issue #39).

Django 6.1 added an ``action_location`` argument to
``ModelAdmin.get_actions()``. Its compatibility shim
(``ModelAdmin._get_actions_with_action_location``) introspects overrides and
emits ``RemovedInDjango70Warning`` for any that still take ``(self, request)``
only; the shim disappears in Django 7.0, where the argument is passed
unconditionally and an outdated override raises ``TypeError``.

``ImageUsageAdmin.get_actions()`` overrides the hook to strip
``delete_selected`` (the registry is a derived index — see
``ImageUsageAdmin.has_delete_permission``), so it has to carry the new
parameter while the package still supports Django 4.2-6.0, where neither the
``ActionLocation`` enum nor the argument exists.
"""

from __future__ import annotations

import inspect
import warnings

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from django_cloudflareimages_toolkit.admin import (
    DEFAULT_ACTION_LOCATION,
    ActionLocation,
    ImageUsageAdmin,
)
from django_cloudflareimages_toolkit.models import ImageUsage

User = get_user_model()

DJANGO_HAS_ACTION_LOCATION = ActionLocation is not None


def _model_admin() -> ImageUsageAdmin:
    return ImageUsageAdmin(ImageUsage, admin.site)


def _request(user):
    request = RequestFactory().get("/")
    request.user = user
    return request


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("boss", "boss@example.com", "pw")


def test_get_actions_declares_action_location_parameter():
    """The override keeps the parameter Django 6.1+ introspects for.

    This is what silences ``RemovedInDjango70Warning`` on 6.1 and what keeps
    the override callable on 7.0, which drops the shim and always passes it.
    """
    params = inspect.signature(ImageUsageAdmin.get_actions).parameters
    assert "action_location" in params
    assert params["action_location"].default is DEFAULT_ACTION_LOCATION


def test_default_action_location_tracks_django_version():
    """The default is the real enum member on 6.1+, ``None`` on older Django."""
    if DJANGO_HAS_ACTION_LOCATION:
        assert DEFAULT_ACTION_LOCATION is ActionLocation.CHANGE_LIST
    else:
        assert DEFAULT_ACTION_LOCATION is None


def test_get_actions_strips_delete_selected(superuser):
    """The whole point of the override survives the signature change."""
    actions = _model_admin().get_actions(_request(superuser))
    assert "delete_selected" not in actions


@pytest.mark.skipif(
    not DJANGO_HAS_ACTION_LOCATION, reason="action_location requires Django >= 6.1"
)
def test_get_actions_accepts_every_action_location(superuser):
    """Each enum member is forwarded to ``super()`` without blowing up."""
    model_admin = _model_admin()
    request = _request(superuser)
    for location in ActionLocation:
        actions = model_admin.get_actions(request, action_location=location)
        assert "delete_selected" not in actions


@pytest.mark.skipif(
    not DJANGO_HAS_ACTION_LOCATION, reason="deprecation shim only exists on Django 6.1"
)
def test_django_shim_does_not_warn(superuser):
    """Django's own call path raises no deprecation warning for this admin."""
    model_admin = _model_admin()
    request = _request(superuser)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        warnings.simplefilter("error", PendingDeprecationWarning)
        actions = model_admin._get_actions_with_action_location(request)
    assert "delete_selected" not in actions
