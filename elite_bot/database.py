"""Database engine, session management, and lightweight schema migration."""

from __future__ import annotations

import logging
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import settings

logger = logging.getLogger(__name__)

from sqlalchemy import event

engine = create_engine(
    settings.database_url,
    future=True,
    connect_args={"timeout": 30},   # wait up to 30s for a lock instead of failing
)

@event.listens_for(engine, "connect")
def _set_wal(conn, _):
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()

#: Columns added after the first release. ``create_all`` will not add columns to
#: an existing table, so they are patched in by :func:`_migrate`.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "subject_books": {
        "book_name": "VARCHAR",
        "academic_year": "VARCHAR",
    },
}



def _migrate() -> None:
    """Add any missing columns in place, preserving existing rows."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue  # create_all already built it with the full schema
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name in present:
                    continue
                logger.info("migrating: adding %s.%s", table, name)
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {name} {ddl}'))


def init_db() -> None:
    """Create tables that do not exist, then patch in any new columns."""
    # Import app models so SQLAlchemy registers them with Base.metadata.
    import backend.models  # noqa: F401

    _migrate()
    Base.metadata.create_all(bind=engine)
