"""Unit tests for the conditional routing function in the orchestrator."""
from app.agents.orchestrator import _route_after_recall


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
