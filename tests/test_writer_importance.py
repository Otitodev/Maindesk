import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

import app.agents.writer as writer_mod
from app.agents.writer import _importance
from app.gateway.schema import PatientMessage, PatientReply


@pytest.mark.parametrize(
    "intent,expected_band",
    [
        ("book_appointment", "high"),
        ("reschedule", "high"),
        ("cancel", "high"),
        ("escalate", "highest"),
        ("ask_question", "mid"),
        ("smalltalk", "low"),
        ("unknown", "low"),
    ],
)
def test_importance_bands(intent, expected_band):
    score = _importance({"intent": intent})
    if expected_band == "highest":
        assert score >= 0.85
    elif expected_band == "high":
        assert 0.6 <= score < 0.9
    elif expected_band == "mid":
        assert 0.3 <= score < 0.6
    else:
        assert score < 0.3


def test_importance_defaults_to_unknown_band():
    assert _importance({}) < 0.3


def _writer_state(intent: str = "ask_question") -> dict:
    return {
        "intent": intent,
        "message": PatientMessage(
            message_id="m", session_id="s", channel="web",
            content="hello", patient_id="p-1",
        ),
        "reply": PatientReply(session_id="s", channel="web", content="hi"),
    }


async def test_log_task_exc_logs_exception_on_failed_task():
    async def _fail():
        raise ValueError("db down")

    task = asyncio.create_task(_fail())
    await asyncio.gather(task, return_exceptions=True)

    with patch.object(writer_mod.log, "error") as mock_error:
        writer_mod._log_task_exc(task)

    mock_error.assert_called_once()
    assert "persist_turn failed" in str(mock_error.call_args)


async def test_log_task_exc_silent_on_success():
    async def _ok():
        return "done"

    task = asyncio.create_task(_ok())
    await task

    with patch.object(writer_mod.log, "error") as mock_error:
        writer_mod._log_task_exc(task)

    mock_error.assert_not_called()


async def test_writer_node_registers_done_callback(monkeypatch):
    registered_callbacks = []

    original_create_task = asyncio.create_task

    def capturing_create_task(coro, **kwargs):
        task = original_create_task(coro, **kwargs)
        original_add = task.add_done_callback

        def recording_add(cb):
            registered_callbacks.append(cb)
            original_add(cb)

        task.add_done_callback = recording_add
        return task

    with patch("app.agents.writer.persist_turn", new_callable=AsyncMock), \
         patch("asyncio.create_task", side_effect=capturing_create_task):
        from app.agents.writer import writer_node
        await writer_node(_writer_state())

    assert len(registered_callbacks) == 1
    assert registered_callbacks[0] is writer_mod._log_task_exc
