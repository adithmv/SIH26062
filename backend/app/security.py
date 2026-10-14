"""Base-station sessions. Local development remains loopback-only."""
import hashlib
import hmac
import secrets
import threading
import re
import ipaddress
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import delete, select, case, or_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session

from .db import get_session
from .config import get_settings
from .models import BaseAccount, BaseSession, BaseDevice, AccessEvent, LoginBudget

router = APIRouter(prefix="/api/auth", tags=["Base access"])
COOKIE = "__Host-polar-session"
PASSWORD_WORK = threading.BoundedSemaphore(2)
PASSWORD_HASHER = PasswordHash.recommended()
# Perform the current password work for unknown users, too.
DUMMY_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))


def enabled():
    return get_settings().mode == "base"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    with PASSWORD_WORK:
        return PASSWORD_HASHER.hash(password)


def verify(password, encoded):
    return verify_and_update(password, encoded)[0]


def verify_and_update(password, encoded):
    """Accept existing scrypt accounts and upgrade only after a valid password."""
    with PASSWORD_WORK:
        if isinstance(encoded, str) and re.fullmatch(r"[0-9a-f]{32}:[0-9a-f]{128}", encoded):
            salt, expected = encoded.split(":")
            value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=131072,
                                   r=8, p=1, maxmem=256 * 1024 * 1024).hex()
            valid = hmac.compare_digest(value, expected)
            return valid, PASSWORD_HASHER.hash(password) if valid else None
        try:
            return PASSWORD_HASHER.verify_and_update(password, encoded)
        except (UnknownHashError, ValueError, TypeError):
            # A damaged record must fail sign-in rather than expose a server error.
            PASSWORD_HASHER.verify(password, DUMMY_HASH)
            return False, None


def now():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def origin_check(request):
    expected = get_settings().origin
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


def consume_login_budget(request, session):
    # Only the ASGI peer is trusted; never read forwarding headers here.
    host = request.client.host if request.client else "unknown"
    try:
        address = ipaddress.ip_address(host)
        host = str(address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address)
    except ValueError:
        host = host.lower()
    timestamp = now().timestamp()
    window = int(timestamp // 60)
    expired = select(LoginBudget.client_hash).where(LoginBudget.window < window - 1).limit(100)
    session.execute(delete(LoginBudget).where(LoginBudget.window < window - 1,
        LoginBudget.client_hash.in_(expired)))
    insert = postgres_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = insert(LoginBudget).values(client_hash=digest(host), window=window, attempts=1)
    statement = statement.on_conflict_do_update(index_elements=[LoginBudget.client_hash], set_={
        "window": window,
        "attempts": case((LoginBudget.window != window, 1), else_=LoginBudget.attempts + 1),
    }, where=or_(LoginBudget.window != window, LoginBudget.attempts < 30)).returning(LoginBudget.attempts)
    count = session.execute(statement).scalar_one_or_none()
    # Commit before password work: multiple workers share the same durable budget.
    session.commit()
    if count is None:
        retry = max(1, 60 - int(timestamp % 60))
        raise HTTPException(429, "Too many sign-in attempts from this connection. Try again shortly.",
                            headers={"Retry-After": str(retry)})


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
    consume_login_budget(request, session)
    account = session.scalar(select(BaseAccount).where(BaseAccount.username == body.username.strip().lower()).with_for_update())
    # Unknown users still perform the password work; responses do not reveal account existence.
    valid, updated_hash = verify_and_update(body.password.get_secret_value(), account.password_hash if account else DUMMY_HASH)
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
    if updated_hash is not None:
        account.password_hash = updated_hash
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
