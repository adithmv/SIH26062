"""Run bounded PMCE sync passes until interrupted."""
import argparse
import logging
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .db import engine
from .pmce import SyncOptions, sync


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "limited", "broadband"], default="offline")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--byte-budget", type=int, default=2048)
    args = parser.parse_args()
    if args.interval < 1:
        parser.error("--interval must be at least 1 second")
    options = SyncOptions(mode=args.mode, byte_budget=args.byte_budget)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        while True:
            try:
                with Session(engine) as session:
                    results = sync(options, session)
                if results:
                    logging.info("PMCE pass: %s", results)
            except HTTPException as exc:
                logging.warning("PMCE: %s", exc.detail)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logging.info("PMCE worker stopped")


if __name__ == "__main__":
    main()
