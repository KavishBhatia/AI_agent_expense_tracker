# conftest.py — patches dash.register_page so page modules can be imported in tests

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True, scope="session")
def _patch_dash_register_page():
    patcher = patch("dash.register_page", return_value=None)
    patcher.start()
    yield
    patcher.stop()
