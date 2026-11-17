import pytest

from core.secrets import SecretBox


def test_roundtrip() -> None:
    box = SecretBox(SecretBox.generate_key())
    token = box.encrypt("api-secret")
    assert token != "api-secret"
    assert box.decrypt(token) == "api-secret"


def test_placeholder_key_rejected() -> None:
    with pytest.raises(ValueError):
        SecretBox("CHANGE_ME_GENERATE_A_REAL_KEY")
