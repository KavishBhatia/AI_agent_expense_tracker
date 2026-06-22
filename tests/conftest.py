# conftest.py — patches dash.register_page so page modules can be imported in tests
#
# Dash 4.x raises PageError if register_page() is called outside an app context.
# The patch must be active during pytest *collection* (import time), before any
# session-scoped fixture would run — so we apply it at module level here.

from unittest.mock import patch as _patch

_register_page_patcher = _patch("dash.register_page", return_value=None)
_register_page_patcher.start()
