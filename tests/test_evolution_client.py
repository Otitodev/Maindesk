from app.gateway.adapters.evolution_client import _to_number


def test_strips_user_jid_suffix():
    assert _to_number("2348012345678@s.whatsapp.net") == "2348012345678"


def test_refuses_group_jid():
    assert _to_number("12345-67890@g.us") is None


def test_bare_number_passes_through():
    assert _to_number("2348012345678") == "2348012345678"


def test_plus_prefixed_number_passes_through():
    assert _to_number("+15551234567") == "+15551234567"
