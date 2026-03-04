from health_log.security import hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    encoded = hash_password("VeryStrongPassword123")
    assert verify_password("VeryStrongPassword123", encoded) is True


def test_password_hash_rejects_invalid_password() -> None:
    encoded = hash_password("VeryStrongPassword123")
    assert verify_password("wrong-password", encoded) is False
