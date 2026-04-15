from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta
from health_log.utils import utcnow
from hashlib import pbkdf2_hmac, sha256

PBKDF2_ALGO = "sha256"
PBKDF2_ITERATIONS = 260_000
SALT_BYTES = 16
TOKEN_BYTES = 48


class InvalidPasswordFormat(ValueError):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    derived = pbkdf2_hmac(PBKDF2_ALGO, password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations_text, salt_hex, digest_hex = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            raise InvalidPasswordFormat("Unsupported password hash scheme")
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError) as exc:
        raise InvalidPasswordFormat("Invalid password hash format") from exc

    actual = pbkdf2_hmac(PBKDF2_ALGO, password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def create_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def expires_in_minutes(minutes: int) -> datetime:
    return utcnow() + timedelta(minutes=minutes)


def expires_in_days(days: int) -> datetime:
    return utcnow() + timedelta(days=days)
