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


class TestAgentBridgeMessages(unittest.TestCase):
    def setUp(self):
        bridge._runner = None

    def tearDown(self):
        bridge._runner = None

    @staticmethod
    def _events(*events):
        async def _gen(*args, **kwargs):
            for e in events:
                yield e
        return _gen

    @staticmethod
    def _event(*texts):
        event = MagicMock()
        event.content.parts = [MagicMock(text=t) for t in texts]
        return event

    def _send(self, run_async_fn, message="hi"):
        import asyncio
        runner, session_service = _make_mock_runner(run_async_fn)
        with patch("expense_tracker_agent.agent_bridge.Runner", return_value=runner), \
             patch("expense_tracker_agent.agent_bridge.InMemorySessionService",
                   return_value=session_service):
            return asyncio.run(bridge._send_message(message)), runner, session_service

    def test_concatenates_text_across_parts_and_events(self):
        events = self._events(self._event("Added ", "expense. "), self._event("Total: 5"))
        text, _, _ = self._send(events)
        self.assertEqual(text, "Added expense. Total: 5")

    def test_returns_done_when_no_text_produced(self):
        text, _, _ = self._send(self._events())
        self.assertEqual(text, "Done.")

    def test_ignores_events_without_content_or_text(self):
        no_content = MagicMock()
        no_content.content = None
        empty_part = MagicMock()
        empty_part.content.parts = [MagicMock(text="")]
        no_parts = MagicMock()
        no_parts.content.parts = []
        text, _, _ = self._send(self._events(no_content, empty_part, no_parts, self._event("ok")))
        self.assertEqual(text, "ok")

    def test_sends_user_message_with_fixed_ids(self):
        captured = {}

        async def _gen(*args, **kwargs):
            captured.update(kwargs)
            return
            yield

        self._send(_gen, message="coffee 3")
        self.assertEqual(captured["user_id"], bridge._USER_ID)
        self.assertEqual(captured["session_id"], bridge._SESSION_ID)
        message = captured["new_message"]
        self.assertEqual(message.role, "user")
        self.assertEqual(message.parts[0].text, "coffee 3")


class TestAgentBridgeSession(unittest.TestCase):
    def setUp(self):
        bridge._runner = None

    def tearDown(self):
        bridge._runner = None

    def test_creates_session_when_missing(self):
        import asyncio
        runner = MagicMock()
        runner.session_service.get_session = AsyncMock(return_value=None)
        runner.session_service.create_session = AsyncMock()
        asyncio.run(bridge._ensure_session(runner))
        runner.session_service.create_session.assert_awaited_once_with(
            app_name=bridge._APP_NAME, user_id=bridge._USER_ID, session_id=bridge._SESSION_ID
        )

    def test_reuses_existing_session(self):
        import asyncio
        runner = MagicMock()
        runner.session_service.get_session = AsyncMock(return_value=MagicMock())
        runner.session_service.create_session = AsyncMock()
        asyncio.run(bridge._ensure_session(runner))
        runner.session_service.create_session.assert_not_awaited()

    def test_runner_is_created_once_and_cached(self):
        with patch("expense_tracker_agent.agent_bridge.Runner") as runner_cls, \
             patch("expense_tracker_agent.agent_bridge.InMemorySessionService"):
            first = bridge._get_runner()
            second = bridge._get_runner()
        self.assertIs(first, second)
        runner_cls.assert_called_once()
        self.assertEqual(runner_cls.call_args.kwargs["app_name"], bridge._APP_NAME)


class TestAgentBridgeLoop(unittest.TestCase):
    def setUp(self):
        import threading

        original_loop = bridge._loop
        threads = []

        def make_thread(*args, **kwargs):
            thread = threading.Thread(*args, **kwargs)
            threads.append((kwargs["target"].__self__, thread))
            return thread

        def cleanup():
            try:
                for loop, thread in threads:
                    if thread.ident is not None:
                        loop.call_soon_threadsafe(loop.stop)
                        thread.join(timeout=5)
                        self.assertFalse(thread.is_alive(), "Background loop did not stop")
                    loop.close()
            finally:
                bridge._loop = original_loop

        self.addCleanup(cleanup)
        bridge._loop = None
        threading_patch = patch.object(bridge, "threading")
        mock_threading = threading_patch.start()
        self.addCleanup(threading_patch.stop)
        mock_threading.Thread.side_effect = make_thread

    def test_loop_is_reused_while_open(self):
        first = bridge._get_loop()
        self.assertIs(first, bridge._get_loop())
        import threading
        ready = threading.Event()
        first.call_soon_threadsafe(ready.set)
        self.assertTrue(ready.wait(timeout=5), "Background loop did not start")

    def test_new_loop_created_when_previous_is_closed(self):
        import asyncio
        closed = asyncio.new_event_loop()
        closed.close()
        bridge._loop = closed
        fresh = bridge._get_loop()
        self.assertIsNot(fresh, closed)
        self.assertFalse(fresh.is_closed())

    def test_chat_runs_on_background_loop_and_returns_text(self):
        async def fake_send(message):
            return f"echo:{message}"

        with patch.object(bridge, "_send_message", fake_send):
            self.assertEqual(bridge.chat("hello"), "echo:hello")


if __name__ == "__main__":
    unittest.main()
