# expense_tracker_agent/agent_bridge.py
import asyncio
import threading
from typing import Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from expense_tracker_agent.agent import root_agent

_APP_NAME = "expense_tracker_dash"
_USER_ID = "dash_user"
_SESSION_ID = "dash_session"

_loop: Optional[asyncio.AbstractEventLoop] = None
_runner: Optional[Runner] = None
_lock = threading.Lock()


def _get_runner() -> Runner:
    global _runner
    if _runner is None:
        session_service = InMemorySessionService()
        _runner = Runner(
            agent=root_agent,
            app_name=_APP_NAME,
            session_service=session_service,
        )
    return _runner


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        t = threading.Thread(target=_loop.run_forever, daemon=True)
        t.start()
    return _loop


async def _ensure_session(runner: Runner) -> None:
    existing = await runner.session_service.get_session(
        app_name=_APP_NAME, user_id=_USER_ID, session_id=_SESSION_ID
    )
    if existing is None:
        await runner.session_service.create_session(
            app_name=_APP_NAME, user_id=_USER_ID, session_id=_SESSION_ID
        )


async def _send_message(message: str) -> str:
    from google.genai.types import Content, Part
    runner = _get_runner()
    await _ensure_session(runner)
    content = Content(role="user", parts=[Part(text=message)])
    response_text = ""
    async for event in runner.run_async(
        user_id=_USER_ID,
        session_id=_SESSION_ID,
        new_message=content,
    ):
        if hasattr(event, "content") and event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    response_text += part.text
    return response_text or "Done."


def chat(message: str) -> str:
    with _lock:
        loop = _get_loop()
        future = asyncio.run_coroutine_threadsafe(_send_message(message), loop)
        return future.result(timeout=60)
