"""Bounded JSON/gzip request handling for PMCE events."""
import gzip
import zlib

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute

MAX_EVENT_BYTES = 65536


def wire_payload(raw, compress):
    compressed = gzip.compress(raw, mtime=0) if compress else raw
    if compress and len(compressed) < len(raw):
        return compressed, "gzip"
    return raw, "identity"


class EventRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def bounded(request: Request):
            if request.method not in ("POST", "PUT"):
                return await handler(request)
            encoding = request.headers.get("content-encoding", "identity")
            if encoding not in ("identity", "gzip"):
                raise HTTPException(415, "Unsupported content encoding.")
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > MAX_EVENT_BYTES:
                    raise HTTPException(413, "Request exceeds 64 KiB.")
            data = bytes(raw)
            if encoding == "gzip":
                try:
                    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    data = decoder.decompress(data, MAX_EVENT_BYTES + 1)
                    if len(data) > MAX_EVENT_BYTES or decoder.unconsumed_tail:
                        raise HTTPException(413, "Expanded request exceeds 64 KiB.")
                    if not decoder.eof or decoder.unused_data:
                        raise HTTPException(400, "Invalid gzip request.")
                except zlib.error:
                    raise HTTPException(400, "Invalid gzip request.") from None
            scope = dict(request.scope)
            scope["headers"] = [(key, value) for key, value in scope["headers"]
                                if key.lower() not in (b"content-encoding", b"content-length")]
            scope["headers"].append((b"content-length", str(len(data)).encode()))

            async def receive():
                return {"type": "http.request", "body": data, "more_body": False}

            return await handler(Request(scope, receive))

        return bounded
