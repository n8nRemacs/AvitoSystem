"""Shared fixtures for tests/web/ — re-exports the profile-form client fixture."""
from __future__ import annotations

# Make the `client` fixture from test_profile_edit_tabs available to all
# tests in this directory without requiring each file to re-define it.
pytest_plugins = ["tests.web.test_profile_edit_tabs"]
