import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./operations.sqlite3"))


def get_session():
    with Session(engine) as session:
        yield session
