import json
from typing import Optional, Dict, Any
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.contrib.auth.models import User
from django.urls import reverse
from django.http import HttpRequest


MAGIC_LINK_SALT = 'prediction_engine_magic_link_salt_v1'


def generate_magic_token(user: User, league_id: Optional[int] = None) -> str:
    """
    Generates a secure, timestamped, cryptographically signed token for a user.
    Optionally embeds a league_id so that logging in switches directly to that pool.
    """
    signer = TimestampSigner(salt=MAGIC_LINK_SALT)
    payload = {
        'user_id': user.id,
        'email': user.email.lower(),
        'league_id': league_id,
    }
    dumped = json.dumps(payload)
    return signer.sign(dumped)


def verify_magic_token(token: str, max_age_seconds: int = 60 * 60 * 24 * 30) -> Optional[Dict[str, Any]]:
    """
    Verifies the magic token and returns the payload dict containing user_id and league_id.
    Default validity is 30 days. Returns None if invalid or expired.
    """
    signer = TimestampSigner(salt=MAGIC_LINK_SALT)
    try:
        raw_payload = signer.unsign(token, max_age=max_age_seconds)
        payload = json.loads(raw_payload)
        return payload
    except (BadSignature, SignatureExpired, ValueError, json.JSONDecodeError):
        return None


def build_magic_login_url(request: Optional[HttpRequest], user: User, league_id: Optional[int] = None) -> str:
    """
    Builds the full absolute magic login URL for the given user and optional pool.
    """
    token = generate_magic_token(user, league_id)
    path = reverse('magic_login', args=[token])
    
    if request:
        return request.build_absolute_uri(path)
    
    return f"https://217.35.171.173:2028{path}"
