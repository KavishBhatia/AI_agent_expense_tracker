# conftest.py — patches dash.register_page so page modules can be imported in tests
from unittest.mock import patch

patch("dash.register_page", return_value=None).start()
