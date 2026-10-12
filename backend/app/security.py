"""Base-station sessions. Local development remains loopback-only."""
import hashlib
import hmac
import os
import secrets
import threading
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import delete, select, func
from sqlalchemy.orm import Session

from .db import get_session
from .models import BaseAccount, BaseSession, BaseDevice, AccessEvent

router = APIRouter(prefix="/api/auth", tags=["Base access"])
COOKIE = "__Host-polar-session"
PASSWORD_WORK = threading.BoundedSemaphore(2)


def enabled():
    return os.getenv("PEM_MODE", "local") == "base"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    with PASSWORD_WORK:
        value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=131072, r=8, p=1, maxmem=256 * 1024 * 1024).hex()
    return salt + ":" + value


def verify(password, encoded):
    return hmac.compare_digest(password_hash(password, encoded.split(":")[0]), encoded)


def now():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def origin_check(request):
    expected = os.getenv("PEM_ORIGIN", "")
    if not expected.startswith("https://") or request.headers.get("origin") != expected:
        raise HTTPException(403, "Use the configured secure base address to make changes.")


def account_for(request, session):
    token = request.cookies.get(COOKIE, "")
    if len(token) > 128:
        return None
    record = session.get(BaseSession, digest(token)) if token else None
    if record is None or utc(record.expires_at) <= now():
        return None
    account = session.get(BaseAccount, record.account_id)
    return account if account and account.active else None


def access_event(session, actor, action, target):
    session.add(AccessEvent(actor=actor, action=action, target=target[:300], created_at=now()))


def authorize(request: Request, session: Session = Depends(get_session)):
    if not enabled():
        return
    path = request.url.path
    if path in {"/api/health", "/api/auth/session", "/api/auth/login"}:
        return
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        device = session.scalar(select(BaseDevice).where(BaseDevice.token_hash == digest(token))) if len(token) <= 128 else None
        if not device or not device.active:
            raise HTTPException(401, "Device credential is invalid or disabled.")
        if request.method != "POST" or path not in {"/api/pmce/events", "/api/files"}:
            raise HTTPException(403, "Device credentials can only deliver events and files.")
        request.state.device = device.name
        access_event(session, device.name, "device.delivery.authorized", path)
        session.commit()
        return
    account = account_for(request, session)
    if not account:
        raise HTTPException(401, "Sign in to the base station.")
    request.state.account = account
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin_check(request)
        read_download = request.method == "POST" and re.fullmatch(r"/api/files/copies/[0-9a-fA-F-]{36}/restore", path)
        if account.role == "viewer" and path != "/api/auth/logout" and not read_download:
            raise HTTPException(403, "Your account has read-only access.")
        access_event(session, account.username, "request.authorized", request.method + " " + path)
        session.commit()


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: SecretStr = Field(min_length=1, max_length=256)


@router.get("/session")
def current(request: Request, response: Response, session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    account = account_for(request, session) if enabled() else None
    return {"mode": "base" if enabled() else "local", "user":
            {"username": account.username, "role": account.role} if account else None}


@router.post("/login")
def login(body: Login, request: Request, response: Response, session: Session = Depends(get_session)):
    if not enabled():
        raise HTTPException(404, "Sign-in is only enabled on the base server.")
    origin_check(request)
    recent = session.scalar(select(func.count()).select_from(AccessEvent).where(
        AccessEvent.action.in_(["login.failed", "login.succeeded"]),
        AccessEvent.created_at > now() - timedelta(minutes=1)))
    if recent >= 30:
        raise HTTPException(429, "Too many sign-in attempts. Wait one minute.", headers={"Retry-After": "60"})
    account = session.scalar(select(BaseAccount).where(BaseAccount.username == body.username.strip().lower()).with_for_update())
    # Unknown users still perform the password work; responses do not reveal account existence.
    dummy = "0" * 32 + ":" + "0" * 128
    valid = verify(body.password.get_secret_value(), account.password_hash if account else dummy)
    locked = account and account.locked_until and utc(account.locked_until) > now()
    if not account or not account.active or locked or not valid:
        if account and not locked:
            account.failures += 1
            if account.failures >= 5:
                account.locked_until = now() + timedelta(minutes=15)
                account.failures = 0
        access_event(session, account.username if account else "unknown", "login.failed", "")
        session.commit()
        raise HTTPException(401, "Sign-in failed. Check your details or wait 15 minutes after repeated failures.")
    account.failures = 0
    account.locked_until = None
    token = secrets.token_urlsafe(32)
    session.execute(delete(BaseSession).where(BaseSession.expires_at <= now()))
    session.add(BaseSession(token_hash=digest(token), account_id=account.id, expires_at=now() + timedelta(hours=8)))
    access_event(session, account.username, "login.succeeded", "")
    session.commit()
    response.set_cookie(COOKIE, token, max_age=8 * 3600, secure=True, httponly=True, samesite="strict", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"username": account.username, "role": account.role}


@router.post("/logout")
def logout(request: Request, response: Response, session: Session = Depends(get_session)):
    session.execute(delete(BaseSession).where(BaseSession.token_hash == digest(request.cookies.get(COOKIE, ""))))
    session.commit()
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="strict", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"signed_out": True}


@router.get("/audit")
def audit_log(request: Request, session: Session = Depends(get_session)):
    if not enabled() or request.state.account.role != "admin":
        raise HTTPException(403, "Administrator access required.")
    rows = session.scalars(select(AccessEvent).order_by(AccessEvent.created_at.desc()).limit(200))
    return [{"actor": r.actor, "action": r.action, "target": r.target, "created_at": r.created_at} for r in rows]
