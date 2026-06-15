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


def test_pending_forces_tools_even_when_smalltalk():
    # A bare "9am"/"yes" mid-flow can score smalltalk/unknown; the pending
    # action must still route to tools so the flow gets executed.
    assert _route_after_recall(
        {"intent": "unknown", "pending": {"type": "book", "slots": []}}
    ) == "tools"


def test_no_pending_smalltalk_still_bypasses_tools():
    assert _route_after_recall({"intent": "smalltalk", "pending": None}) == "reasoner"
