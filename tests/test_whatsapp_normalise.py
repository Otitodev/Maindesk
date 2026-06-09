from app.gateway.adapters.whatsapp import _normalise


def test_typical_text_payload():
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": "2348012345678@s.whatsapp.net", "id": "wamid-1"},
            "message": {"conversation": "Hi, can I book Tuesday?"},
        },
    }
    msg = _normalise(payload)
    assert msg.channel == "whatsapp"
    assert msg.session_id == "whatsapp:2348012345678@s.whatsapp.net"
    assert msg.message_id == "wamid-1"
    assert msg.content == "Hi, can I book Tuesday?"
    assert msg.media_url is None
    assert msg.platform_meta["raw_from"] == "2348012345678@s.whatsapp.net"


def test_extended_text_payload():
    payload = {
        "data": {
            "key": {"remoteJid": "abc@s.whatsapp.net", "id": "wamid-2"},
            "message": {"extendedTextMessage": {"text": "reschedule please"}},
        },
    }
    msg = _normalise(payload)
    assert msg.content == "reschedule please"


def test_image_message_captures_media_url():
    payload = {
        "data": {
            "key": {"remoteJid": "abc@s.whatsapp.net", "id": "wamid-3"},
            "message": {"imageMessage": {"url": "https://media.example/x.jpg"}},
        },
    }
    msg = _normalise(payload)
    assert msg.media_url == "https://media.example/x.jpg"


def test_missing_fields_default_to_unknown():
    msg = _normalise({})
    assert msg.message_id == "unknown"
    assert msg.session_id == "whatsapp:unknown"
    assert msg.content == ""
    assert msg.media_url is None
