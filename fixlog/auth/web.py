from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from fixlog.auth.deps import account_from_authorization
from fixlog.config import Settings
from fixlog.db.models import Account, AccountStatus

WEB_SESSION_COOKIE = "fixlog_web_session"


def create_web_session_cookie(account: Account, settings: Settings) -> str:
    if not settings.fixlog_web_secret_key:
        raise RuntimeError("FIXLOG_WEB_SECRET_KEY is required for browser login")
    payload = {
        "account_id": str(account.id),
        "token_hash": account.api_token_hash,
        "exp": int(time.time()) + settings.fixlog_web_session_ttl_seconds,
    }
    body = _base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_signature(body, settings)}"


def account_from_request(
    request: Request,
    db: Session,
    settings: Settings,
) -> Account | None:
    authorization = request.headers.get("authorization")
    if authorization:
        try:
            return account_from_authorization(authorization, db)
        except HTTPException:
            return None

    cookie_value = request.cookies.get(WEB_SESSION_COOKIE)
    if not cookie_value:
        return None
    return account_from_web_cookie(cookie_value, db, settings)


def account_from_web_cookie(
    cookie_value: str,
    db: Session,
    settings: Settings,
) -> Account | None:
    if not settings.fixlog_web_secret_key:
        return None
    try:
        body, provided_signature = cookie_value.split(".", 1)
    except ValueError:
        return None
    expected_signature = _signature(body, settings)
    if not hmac.compare_digest(provided_signature, expected_signature):
        return None

    try:
        payload = json.loads(_base64url_decode(body))
        account_id = UUID(str(payload["account_id"]))
        token_hash = str(payload["token_hash"])
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if expires_at < int(time.time()):
        return None

    return db.scalar(
        select(Account).where(
            Account.id == account_id,
            Account.api_token_hash == token_hash,
            Account.status == AccountStatus.ACTIVE,
        )
    )


def _signature(body: str, settings: Settings) -> str:
    digest = hmac.new(
        settings.fixlog_web_secret_key.encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _base64url(digest)


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")
