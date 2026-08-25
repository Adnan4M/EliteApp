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
    "study_pairs": {
        "invite_code": "VARCHAR",
        "user_b_id": "INTEGER",
    },
    "app_users": {
        "gender": "VARCHAR",
        "active_skin_id": "INTEGER",
    },
    "subject_chapters": {
        "page_start": "INTEGER",
        "page_end": "INTEGER",
        "chapter_number": "INTEGER",
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

        # Fix study_pairs.user_b_id which was created NOT NULL but must be nullable.
        if "study_pairs" in existing_tables:
            cols = {c["name"]: c for c in inspector.get_columns("study_pairs")}
            ub = cols.get("user_b_id")
            if ub is not None and not ub.get("nullable", True):
                logger.info("migrating: recreating study_pairs to make user_b_id nullable")
                conn.execute(text("""
                    CREATE TABLE study_pairs_new (
                        id INTEGER PRIMARY KEY,
                        user_a_id INTEGER NOT NULL,
                        user_b_id INTEGER,
                        invite_code VARCHAR UNIQUE,
                        status VARCHAR DEFAULT 'pending',
                        created_at DATETIME
                    )
                """))
                conn.execute(text("""
                    INSERT INTO study_pairs_new
                        SELECT id, user_a_id, user_b_id, invite_code, status, created_at
                        FROM study_pairs
                """))
                conn.execute(text("DROP TABLE study_pairs"))
                conn.execute(text("ALTER TABLE study_pairs_new RENAME TO study_pairs"))


_DEFAULT_SKINS = [
    # (name, type_key, bg_color, price_xp, gender, sort_order)
    # type_key is used by CharacterWidget to select the character design
    ("Scientist",  "scientist",  "#c62f2f", 0,   None, 0),
    ("Star",       "star",       "#c66b2f", 0,   None, 1),
    ("Atom",       "atom",       "#c6a82f", 100, None, 2),
    ("Planet",     "planet",     "#a8c62f", 100, None, 3),
    ("Cell",       "cell",       "#6bc62f", 150, None, 4),
    ("Molecule",   "molecule",   "#2fc62f", 150, None, 5),
    ("DNA",        "dna",        "#2fc66b", 200, None, 6),
    ("Crystal",    "crystal",    "#2fc6a8", 200, None, 7),
    ("Galaxy",     "galaxy",     "#2fa8c6", 300, None, 8),
    ("Fossil",     "fossil",     "#2f6bc6", 300, None, 9),
    ("Element",    "element",    "#2f2fc6", 400, None, 10),
    ("Microscope", "microscope", "#6b2fc6", 400, None, 11),
    ("Compass",    "compass",    "#a82fc6", 500, None, 12),
    ("Energy",     "energy",     "#c62fa8", 500, None, 13),
    ("Ecosystem",  "ecosystem",  "#c62f6b", 800, None, 14),
]


def init_db() -> None:
    """Create tables that do not exist, then patch in any new columns."""
    # Import app models so SQLAlchemy registers them with Base.metadata.
    import backend.models  # noqa: F401
    from backend.models import Skin

    _migrate()
    Base.metadata.create_all(bind=engine)

    # Seed / re-seed skins — replace old emoji-based entries with new type-key entries
    _new_keys = {r[1] for r in _DEFAULT_SKINS}
    with SessionLocal() as db:
        existing = db.query(Skin).all()
        # If any skin uses the old emoji style (contains non-ASCII), wipe and re-seed
        needs_reseed = (not existing) or any(
            s.emoji not in _new_keys for s in existing
        )
        if needs_reseed:
            for s in existing:
                db.delete(s)
            db.flush()
            for name_ar, emoji, bg_color, price_xp, gender, sort_order in _DEFAULT_SKINS:
                db.add(Skin(
                    name_ar=name_ar, emoji=emoji, bg_color=bg_color,
                    price_xp=price_xp, gender=gender, sort_order=sort_order,
                ))
            db.commit()
            logger.info("seeded %d skins (Word Atlas set)", len(_DEFAULT_SKINS))
