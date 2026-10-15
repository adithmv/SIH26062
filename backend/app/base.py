"""Read-only base station readiness and reception summary."""
import shutil
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .db import get_session
from .files import FileRoute, root
from .models import BaseDevice, ManagedFile, PMCEReceipt
from .security import enabled

router = APIRouter(prefix="/api/base", tags=["Base station"], route_class=FileRoute)


@router.get("/status")
def status(request: Request, session: Session = Depends(get_session)):
    if not enabled():
        raise HTTPException(404, "This server is not configured as a base station.")
    storage = root()
    disk = shutil.disk_usage(storage)
    return {"checked_at": datetime.now(timezone.utc), "storage_root": str(storage),
            "free_bytes": disk.free, "storage_warning": disk.free < 512 * 1024 * 1024,
            "stored_files": session.scalar(select(func.count()).select_from(ManagedFile)),
            "received_events": session.scalar(select(func.count()).select_from(PMCEReceipt)),
            "last_received_at": session.scalar(select(func.max(PMCEReceipt.received_at))),
            "devices": [{"name": d.name, "active": d.active} for d in session.scalars(select(BaseDevice).order_by(BaseDevice.name))]
            if request.state.account.role == "admin" else None}
