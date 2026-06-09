import pytest

from app.agents.writer import _importance


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
