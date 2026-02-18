import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Optional


def get_secret_key() -> str:
    secret = os.getenv('APP_SECRET_KEY', '').strip()
    if not secret or secret == 'change-me-in-production':
        raise RuntimeError('APP_SECRET_KEY must be set to a strong secret in environment')
    return secret


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 120_000)
    return f'pbkdf2$120000${salt}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, hashed = stored.split('$', 3)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(digest.hex(), hashed)
    except Exception:
        return False


def create_session_token(user_id: int, user_type: str, ttl: int = 60 * 60 * 24 * 7) -> str:
    exp = int(time.time()) + ttl
    payload = f'{user_id}:{user_type}:{exp}'
    sig = hmac.new(get_secret_key().encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = f'{payload}:{sig}'
    return base64.urlsafe_b64encode(token.encode()).decode()


def verify_session_token(token: str) -> Optional[dict]:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, user_type, exp, sig = raw.rsplit(':', 3)
        payload = f'{user_id}:{user_type}:{exp}'
        expected = hmac.new(get_secret_key().encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if int(exp) < int(time.time()):
            return None
        return {'user_id': int(user_id), 'user_type': user_type}
    except Exception:
        return None
