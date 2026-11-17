import pytest

from api.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from core.settings import Settings


def test_password_roundtrip() -> None:
    h = hash_password("correct horse")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)


def test_access_token_roundtrip_and_tamper() -> None:
    s = Settings(jwt_secret="unit-test-secret")  # type: ignore[arg-type]
    tok = create_access_token(7, "a@b.c", ["owner"], s)
    claims = decode_access_token(tok, s)
    assert claims["sub"] == "7" and claims["roles"] == ["owner"]
    with pytest.raises(TokenError):
        decode_access_token(tok + "x", s)
    with pytest.raises(TokenError):
        decode_access_token(tok, Settings(jwt_secret="other"))  # type: ignore[arg-type]


def test_refresh_token_is_random_and_hashed() -> None:
    a, b = new_refresh_token(), new_refresh_token()
    assert a != b and len(a) > 40
    assert hash_refresh_token(a) != a and len(hash_refresh_token(a)) == 64
