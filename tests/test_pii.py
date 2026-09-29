from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD của tôi là 079203001234")
    assert "079203001234" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card_formats() -> None:
    card_numbers = (
        "4111111111111111",
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
    )

    for card_number in card_numbers:
        out = scrub_text(f"Card: {card_number}")
        assert card_number not in out
        assert "REDACTED_CREDIT_CARD" in out


def test_scrub_multiple_pii_types_in_one_text() -> None:
    out = scrub_text("Mail a@b.com, phone 0987654321, card 4111 1111 1111 1111")
    assert "a@b.com" not in out
    assert "0987654321" not in out
    assert "4111 1111 1111 1111" not in out
