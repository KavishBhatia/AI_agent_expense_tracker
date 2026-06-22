# tests/test_agent_bridge.py
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import expense_tracker_agent.agent_bridge as bridge


def _failing_run_async(exc):
    """Return a callable that produces an async generator raising `exc` on first iteration."""
    async def _gen(*args, **kwargs):
        raise exc
        yield  # makes it an async generator
    return _gen


def _succeeding_run_async(text="Done."):
    """Return a callable that produces an async generator yielding one text event."""
    async def _gen(*args, **kwargs):
        event = MagicMock()
        event.content.parts = [MagicMock(text=text)]
        yield event
    return _gen


def _make_mock_runner(run_async_fn):
    session_service = MagicMock()
    session_service.get_session = AsyncMock(return_value=MagicMock())
    runner = MagicMock()
    runner.session_service = session_service
    runner.run_async = run_async_fn
    return runner, session_service


class TestAgentBridgeSessionReset(unittest.TestCase):
    def setUp(self):
        bridge._runner = None

    def tearDown(self):
        bridge._runner = None

    def test_runner_reset_to_none_on_exception(self):
        """When run_async raises, _runner must be reset to None to prevent stale session replay."""
        mock_runner, mock_ss = _make_mock_runner(_failing_run_async(RuntimeError("rate limit")))

        with patch("expense_tracker_agent.agent_bridge.Runner", return_value=mock_runner), \
             patch("expense_tracker_agent.agent_bridge.InMemorySessionService", return_value=mock_ss):
            with self.assertRaises(RuntimeError):
                bridge.chat("9.99 at Aldi for Medjool Dates")

        self.assertIsNone(bridge._runner,
                          "_runner must be None after an exception so next call gets a fresh session")

    def test_runner_not_reset_on_success(self):
        """On a successful call, _runner must remain set (session reuse)."""
        mock_runner, mock_ss = _make_mock_runner(_succeeding_run_async("Added expense."))

        with patch("expense_tracker_agent.agent_bridge.Runner", return_value=mock_runner), \
             patch("expense_tracker_agent.agent_bridge.InMemorySessionService", return_value=mock_ss):
            result = bridge.chat("5 coffee")

        self.assertIsNotNone(bridge._runner,
                             "_runner must stay set after a successful call")
        self.assertEqual(result, "Added expense.")

    def test_exception_type_is_preserved(self):
        """The original exception type must propagate unchanged through chat()."""
        class FakeRateLimitError(Exception):
            pass

        mock_runner, mock_ss = _make_mock_runner(_failing_run_async(FakeRateLimitError("quota")))

        with patch("expense_tracker_agent.agent_bridge.Runner", return_value=mock_runner), \
             patch("expense_tracker_agent.agent_bridge.InMemorySessionService", return_value=mock_ss):
            with self.assertRaises(FakeRateLimitError):
                bridge.chat("test")


if __name__ == "__main__":
    unittest.main()
