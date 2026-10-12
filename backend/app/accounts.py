"""Manage base accounts from the server console, never through public signup."""
import argparse
import getpass
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import engine
from .models import BaseAccount, BaseSession
from .security import access_event, password_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["set", "disable"])
    parser.add_argument("username")
    parser.add_argument("--role", choices=["admin", "operator", "viewer"], default="operator")
    args = parser.parse_args()
    username = args.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9._@-]{1,80}", username):
        parser.error("Use 1–80 letters, numbers, dots, underscores, @ or hyphens.")
    password = None
    if args.action == "set":
        password = getpass.getpass("New password (at least 14 characters): ")
        if not 14 <= len(password) <= 256 or password != getpass.getpass("Repeat password: "):
            parser.error("Passwords must match and contain 14–256 characters.")
    with Session(engine) as session:
        account = session.scalar(select(BaseAccount).where(BaseAccount.username == username))
        if account is None:
            if args.action == "disable":
                parser.error("Account not found.")
            account = BaseAccount(username=username)
            session.add(account)
        else:
            session.execute(delete(BaseSession).where(BaseSession.account_id == account.id))
        if password is not None:
            account.password_hash = password_hash(password)
            account.role = args.role
            account.active = True
            account.failures = 0
            account.locked_until = None
        else:
            account.active = False
        access_event(session, "server-console", "account." + args.action, username)
        session.commit()
    print("Account updated. Existing sessions have been revoked.")


if __name__ == "__main__":
    main()
