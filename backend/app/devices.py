"""Issue or revoke a field-device delivery token on the base console."""
import argparse
import secrets
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import engine
from .models import BaseDevice
from .security import access_event, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["issue", "disable"])
    parser.add_argument("name")
    args = parser.parse_args()
    if not 1 <= len(args.name) <= 80 or not args.name.isprintable():
        parser.error("Use a device name of 1–80 printable characters.")
    token = secrets.token_urlsafe(32)
    with Session(engine) as session:
        device = session.scalar(select(BaseDevice).where(BaseDevice.name == args.name))
        if not device:
            if args.action == "disable":
                parser.error("Device not found.")
            device = BaseDevice(name=args.name)
            session.add(device)
        device.active = args.action == "issue"
        device.token_hash = digest(token)
        access_event(session, "server-console", "device." + args.action, args.name)
        session.commit()
    if args.action == "issue":
        print("Store this delivery token securely on the field device. It is shown only once:")
        print(token)
    else:
        print("Device access revoked.")


if __name__ == "__main__":
    main()
