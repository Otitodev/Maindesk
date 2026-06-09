import hashlib
import hmac

from app.gateway.adapters.whatsapp import _verify_hmac, _verify_token

SECRET = "shh-secret"


def _sig(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---- HMAC ----

def test_hmac_valid_raw_hex_passes():
    body = b'{"event":"messages.upsert"}'
    assert _verify_hmac(body, _sig(body), SECRET) is True


def test_hmac_valid_sha256_prefixed_passes():
    body = b'{"event":"messages.upsert"}'
    assert _verify_hmac(body, f"sha256={_sig(body)}", SECRET) is True


def test_hmac_wrong_signature_fails():
    body = b'{"event":"messages.upsert"}'
    assert _verify_hmac(body, "deadbeef", SECRET) is False


def test_hmac_missing_signature_fails():
    assert _verify_hmac(b"body", None, SECRET) is False


def test_hmac_wrong_secret_fails():
    body = b"hello"
    good_with_other_secret = _sig(body, "different")
    assert _verify_hmac(body, good_with_other_secret, SECRET) is False


# ---- token + IP allowlist ----

def test_token_match_empty_allowlist_passes():
    assert _verify_token("tok", "tok", "10.0.0.1", []) is True


def test_token_match_ip_in_allowlist_passes():
    assert _verify_token("tok", "tok", "10.0.0.5", ["10.0.0.0/24"]) is True


def test_token_match_ip_outside_allowlist_fails():
    assert _verify_token("tok", "tok", "192.168.1.5", ["10.0.0.0/24"]) is False


def test_token_mismatch_fails():
    assert _verify_token("bad", "tok", "10.0.0.5", []) is False


def test_token_missing_fails():
    assert _verify_token(None, "tok", "10.0.0.5", []) is False


def test_token_bad_client_ip_fails():
    assert _verify_token("tok", "tok", "not-an-ip", ["10.0.0.0/24"]) is False


def test_token_bad_cidr_skipped():
    # A malformed CIDR shouldn't crash — just doesn't match.
    assert _verify_token("tok", "tok", "10.0.0.5", ["not-a-cidr"]) is False
    assert _verify_token("tok", "tok", "10.0.0.5", ["not-a-cidr", "10.0.0.0/24"]) is True
