"""
Pytest configuration for django-cloudflareimages-toolkit tests.

Note: Django setup is handled by the root-level conftest.py.
This file can contain test-specific fixtures.
"""

import pytest
from django.utils import deprecation


def pytest_collection_modifyitems(items):
    """Fail any test that touches an API Django 7.0 removes.

    ``RemovedInDjango70Warning`` only exists on Django 6.1+, so on older series
    this is a no-op and the 6.1 CI legs carry the guard.
    """
    if hasattr(deprecation, "RemovedInDjango70Warning"):
        mark = pytest.mark.filterwarnings(
            "error::django.utils.deprecation.RemovedInDjango70Warning"
        )
        for item in items:
            item.add_marker(mark)
