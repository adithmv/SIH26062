"""Bounded, read-only reachability checks for a local-network PEM backend."""
import asyncio
import ipaddress
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/connection", tags=["Connection"])


class Check(BaseModel):
    address: str = Field(min_length=1, max_length=250)


def normalize(address):
    try:
        url = urlsplit(address.strip())
        if url.scheme not in {"http", "https"} or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
            raise ValueError()
        host = url.hostname
        port = url.port
        if not host or (port is not None and not 1 <= port <= 65535):
            raise ValueError()
        if host != "localhost":
            ip = ipaddress.ip_address(host)
            allowed = [ipaddress.ip_network(net) for net in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7")]
            if not any(ip in net for net in allowed):
                raise ValueError()
        host = f"[{host}]" if ":" in host else host
        return f"{url.scheme}://{host}" + (f":{port}" if port else "")
    except ValueError:
        raise HTTPException(400, "Enter http:// or https:// followed by localhost or a private network IP and port. Do not include a path, password or query.") from None


@router.post("/check")
async def check_connection(body: Check):
    address = normalize(body.address)
    started = time.monotonic()
    reachable = False
    version = None
    message = "Connection failed."
    try:
        async with asyncio.timeout(10):
            async with httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False) as client:
                async with client.stream("GET", address + "/api/health") as response:
                    if response.status_code in {401, 403}:
                        message = "The other device requires authorization. This connection check does not support sign-in yet."
                    elif response.status_code != 200:
                        message = f"The other device returned HTTP {response.status_code}. Check its backend and address."
                    else:
                        data = b""
                        async for chunk in response.aiter_bytes():
                            data += chunk
                            if len(data) > 4096:
                                raise ValueError()
                        health = json.loads(data)
                        if not isinstance(health, dict) or health.get("status") != "ok" or not isinstance(health.get("version"), str) or len(health["version"]) > 40:
                            raise ValueError()
                        reachable, version = True, health["version"]
                        message = "Backend health check passed. File browsing and transfer are not connected yet."
    except (TimeoutError, httpx.TimeoutException):
        message = "Connection timed out. Check that the other device is on the network and its backend is running."
    except httpx.RequestError:
        message = "Cannot reach the other backend. Check its address, port, network and firewall."
    except (ValueError, UnicodeError):
        message = "The address did not return a valid Polar Expedition Manager health response."
    return JSONResponse({"address": address, "reachable": reachable, "message": message,
                         "checked_at": datetime.now(timezone.utc).isoformat(),
                         "response_ms": round((time.monotonic() - started) * 1000) if reachable else None,
                         "version": version}, headers={"Cache-Control": "no-store"})
