def test_normalize_recipient_phone_local_format():
    from app.integrations.whatsapp_meta import _normalize_recipient_phone

    assert _normalize_recipient_phone("87782304206") == "77782304206"


def test_normalize_recipient_phone_strips_non_digits():
    from app.integrations.whatsapp_meta import _normalize_recipient_phone

    assert _normalize_recipient_phone("+7 (778) 230-42-06") == "77782304206"