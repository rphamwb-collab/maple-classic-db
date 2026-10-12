"""Database connection setup.

- engine:       the connection to data/maple.db
- SessionLocal: makes a new database session (a "conversation" with the DB)
- get_db():     FastAPI dependency - gives each web request its own session
- init_db():    creates any tables that don't exist yet
"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Project root = the folder that contains app/ and data/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "maple.db"
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

DATA_DIR.mkdir(exist_ok=True)

# check_same_thread=False lets FastAPI use the SQLite connection from worker threads.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """Use in a route like: def page(db: Session = Depends(get_db))."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables (does nothing to tables that already exist)."""
    from app import models  # imported here so all table classes are registered

    models.Base.metadata.create_all(bind=engine)
