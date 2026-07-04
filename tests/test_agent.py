"""
Tests for expense_tracker_agent/agent.py.

The agent instruction tests cover the instruction string content.
The runner tests verify tool execution via the ADK runner with proper function-call ID correlation
(required since ADK 1.21.0).
"""
import asyncio
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, FinishReason, FunctionCall, FunctionResponse, Part

from expense_tracker_agent.agent import _build_instruction, root_agent
from expense_tracker_agent import tools
import expense_tracker_agent.db as db_module
from expense_tracker_agent.db import init_db, fetch_expenses, insert_expense


def _temp_db() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return Path(f.name)


# ---------------------------------------------------------------------------
# Agent instruction tests
# ---------------------------------------------------------------------------

class TestAgentInstruction(unittest.TestCase):

    def setUp(self):
        self.instruction = _build_instruction(today="2026-06-03")

    def test_instruction_contains_today_date(self):
        self.assertIn("2026-06-03", self.instruction)

    def test_instruction_contains_all_categories(self):
        for cat in ["Groceries", "Commute", "Entertainment", "Alcohol", "Miscellaneous"]:
            self.assertIn(cat, self.instruction)

    def test_instruction_mentions_category_inference(self):
        self.assertIn("infer", self.instruction.lower())

    def test_instruction_mentions_merchant(self):
        self.assertIn("merchant", self.instruction.lower())

    def test_instruction_mentions_date_resolution(self):
        self.assertIn("yesterday", self.instruction.lower())

    def test_root_agent_instruction_contains_todays_date(self):
        today = date.today().isoformat()
        self.assertIn(today, root_agent.instruction)


# ---------------------------------------------------------------------------
# Agent configuration tests
# ---------------------------------------------------------------------------

class TestAgentConfiguration(unittest.TestCase):

    def test_agent_has_add_expense_tool(self):
        tool_names = [t.__name__ for t in root_agent.tools]
        self.assertIn("add_expense", tool_names)

    def test_agent_has_calculate_total_spending_tool(self):
        tool_names = [t.__name__ for t in root_agent.tools]
        self.assertIn("calculate_total_spending", tool_names)

    def test_agent_has_get_spending_by_category_tool(self):
        tool_names = [t.__name__ for t in root_agent.tools]
        self.assertIn("get_spending_by_category", tool_names)

    def test_agent_has_list_recent_expenses_tool(self):
        tool_names = [t.__name__ for t in root_agent.tools]
        self.assertIn("list_recent_expenses", tool_names)


# ---------------------------------------------------------------------------
# ADK runner integration tests (ADK 1.21.0+)
# Uses real session + runner; mocks only the Gemini generate_content_async call.
# Function call IDs are auto-assigned by ADK and must be propagated into the
# FunctionResponse so ADK can correlate call→response.
# ---------------------------------------------------------------------------

class TestAgentRunner(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.tmp_db = _temp_db()
        self.db_patcher = patch.object(db_module, "DB_PATH", self.tmp_db)
        self.db_patcher.start()
        init_db()

    def tearDown(self):
        self.db_patcher.stop()
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    async def _make_runner(self):
        app_name = "test_app"
        user_id = "test_user"
        session_id = "test_session"
        session_service = InMemorySessionService()
        runner = Runner(agent=root_agent, app_name=app_name,
                        session_service=session_service)
        await session_service.create_session(
            app_name=app_name, user_id=user_id, session_id=session_id)
        return runner, app_name, user_id, session_id

    async def test_add_expense_tool_called(self):
        """Agent calls add_expense when user describes an expense."""
        runner, app_name, user_id, session_id = await self._make_runner()
        call_id = "test-call-001"

        async def fake_generate(llm_request, stream=False):
            has_fn_response = any(
                p.function_response is not None
                for c in (llm_request.contents or [])
                for p in (c.parts or [])
            )
            if has_fn_response:
                yield _text_chunk("I have added your expense.")
            else:
                yield _fn_call_chunk(
                    "add_expense",
                    {"amount": 10.5, "description": "Lunch", "category": "Food"},
                    call_id,
                )

        with unittest.mock.patch(
            "google.adk.models.Gemini.generate_content_async",
            side_effect=fake_generate,
        ):
            msg = Content(role="user",
                          parts=[Part(text="Add lunch expense 10.50")])
            events = []
            async for event in runner.run_async(
                user_id=user_id, session_id=session_id, new_message=msg
            ):
                events.append(event)

        rows = fetch_expenses()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["amount"], 10.5)

    async def test_list_expenses_returns_content(self):
        """Agent calls list_recent_expenses and returns results."""
        today = date.today().isoformat()
        insert_expense(10.5, "Food", "Lunch", date=today)
        insert_expense(25.0, "Commute", "Taxi", date=today)

        runner, app_name, user_id, session_id = await self._make_runner()
        call_id = "test-call-002"

        async def fake_generate(llm_request, stream=False):
            has_fn_response = any(
                p.function_response is not None
                for c in (llm_request.contents or [])
                for p in (c.parts or [])
            )
            if has_fn_response:
                result = tools.list_recent_expenses(count=2)
                yield _text_chunk(f"Here are your expenses: {result}")
            else:
                yield _fn_call_chunk("list_recent_expenses", {"count": 2}, call_id)

        with unittest.mock.patch(
            "google.adk.models.Gemini.generate_content_async",
            side_effect=fake_generate,
        ):
            msg = Content(role="user", parts=[Part(text="List my last 2 expenses")])
            events = []
            async for event in runner.run_async(
                user_id=user_id, session_id=session_id, new_message=msg
            ):
                events.append(event)

        final = events[-1]
        self.assertTrue(final.is_final_response())
        text = final.content.parts[0].text
        self.assertIn("Lunch", text)
        self.assertIn("Taxi", text)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

import unittest.mock
from google.adk.events import Event


def _text_chunk(text: str):
    """Fake LLM response chunk with a text part."""
    return _FakeLLMResponse(Content(parts=[Part(text=text)]))


def _fn_call_chunk(name: str, args: dict, call_id: str):
    """Fake LLM response chunk with a function call part."""
    fc = FunctionCall(name=name, args=args, id=call_id)
    return _FakeLLMResponse(Content(role="model", parts=[Part(function_call=fc)]))


class _FakeLLMResponse:
    def __init__(self, content):
        self.content = content
        self.usage_metadata = None
        self.finish_reason = FinishReason.STOP
        self.model_version = None
        self.partial = False

    def model_dump(self, **kwargs):
        return {
            "content": self.content,
            "usage_metadata": self.usage_metadata,
            "finish_reason": self.finish_reason,
            "partial": self.partial,
        }


if __name__ == "__main__":
    unittest.main()
