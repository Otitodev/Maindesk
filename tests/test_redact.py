from app.gateway.redact import redact


def test_bearer_token_redacted():
    assert "[REDACTED:TOKEN]" in redact("Authorization: Bearer abc123XYZ.token-value")


def test_api_key_redacted():
    assert "[REDACTED:KEY]" in redact("use sk_live_ABCD1234EFGH5678WXYZ to auth")


def test_card_number_redacted():
    assert "[REDACTED:CARD]" in redact("card is 4111 1111 1111 1111 please")


def test_ssn_redacted():
    assert "[REDACTED:SSN]" in redact("SSN 123-45-6789 on file")


def test_jwt_redacted():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcDEF_xyz123"
    assert "[REDACTED:JWT]" in redact(f"token={jwt}")


def test_benign_text_unchanged():
    text = "Your appointment is at 3pm on Tuesday with Dr. Lee."
    assert redact(text) == text


def test_empty_returns_empty():
    assert redact("") == ""


def test_idempotent():
    msg = "SSN 123-45-6789 and Bearer xyz"
    once = redact(msg)
    twice = redact(once)
    assert once == twice


def test_multiple_secrets_in_one_message():
    out = redact("SSN 111-22-3333 plus Bearer abc.def")
    assert "[REDACTED:SSN]" in out
    assert "[REDACTED:TOKEN]" in out
    assert "111-22-3333" not in out
