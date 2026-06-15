"""Unit tests for the conditional routing functions in the orchestrator."""
import app.agents.orchestrator as orch
from app.agents.orchestrator import _route_after_recall, _route_after_triage


def test_smalltalk_bypasses_tools():
    assert _route_after_recall({"intent": "smalltalk"}) == "reasoner"


def test_unknown_bypasses_tools():
    assert _route_after_recall({"intent": "unknown"}) == "reasoner"


def test_missing_intent_defaults_to_reasoner():
    assert _route_after_recall({}) == "reasoner"


def test_book_appointment_routes_to_tools():
    assert _route_after_recall({"intent": "book_appointment"}) == "tools"


def test_reschedule_routes_to_tools():
    assert _route_after_recall({"intent": "reschedule"}) == "tools"


def test_cancel_routes_to_tools():
    assert _route_after_recall({"intent": "cancel"}) == "tools"


def test_escalate_routes_to_tools():
    assert _route_after_recall({"intent": "escalate"}) == "tools"


def test_ask_question_routes_to_tools():
    assert _route_after_recall({"intent": "ask_question"}) == "tools"


def test_pending_forces_tools_even_when_smalltalk():
    # A bare "9am"/"yes" mid-flow can score smalltalk/unknown; the pending
    # action must still route to tools so the flow gets executed.
    assert _route_after_recall(
        {"intent": "unknown", "pending": {"type": "book", "slots": []}}
    ) == "tools"


def test_no_pending_smalltalk_still_bypasses_tools():
    assert _route_after_recall({"intent": "smalltalk", "pending": None}) == "reasoner"


def test_route_after_triage_hands_off_when_deferring(monkeypatch):
    monkeypatch.setattr(orch, "should_defer_to_staff", lambda *a, **k: True)
    assert _route_after_triage({}) == "handoff"


def test_route_after_triage_recalls_when_not_deferring(monkeypatch):
    monkeypatch.setattr(orch, "should_defer_to_staff", lambda *a, **k: False)
    assert _route_after_triage({}) == "recall"
