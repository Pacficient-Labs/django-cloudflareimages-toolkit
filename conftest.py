"""
Root-level pytest configuration for django-cloudflareimages-toolkit tests.

pytest-django handles Django setup automatically via DJANGO_SETTINGS_MODULE
from pyproject.toml. This conftest.py just ensures the project root is in the path.
"""

import os
import sys

# Ensure the project root is FIRST in the path to override any installed packages
project_root = os.path.dirname(os.path.abspath(__file__))

# Remove the project root if it exists elsewhere and add it at the front
sys.path = [
    p for p in sys.path if os.path.normpath(p) != os.path.normpath(project_root)
]
sys.path.insert(0, project_root)
