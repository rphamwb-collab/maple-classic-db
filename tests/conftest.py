"""Shared test setup.

The tests use their OWN temporary database (seeded with the sample data),
so running them never touches your real data/maple.db.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as app_db
import scraper.seed_sample as seed_sample


@pytest.fixture(scope="session")
def test_sessionmaker(tmp_path_factory):
    """Point the app and the seed script at a temporary database, then seed it."""
    db_file = tmp_path_factory.mktemp("db") / "test.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    # Swap the real database for the temporary one everywhere it is used.
    mp = pytest.MonkeyPatch()
    mp.setattr(app_db, "engine", engine)
    mp.setattr(app_db, "SessionLocal", TestSession)
    mp.setattr(seed_sample, "engine", engine)
    mp.setattr(seed_sample, "SessionLocal", TestSession)

    seed_sample.seed()
    yield TestSession

    mp.undo()
    engine.dispose()


@pytest.fixture
def db(test_sessionmaker):
    """A database session for checking data directly in a test."""
    with test_sessionmaker() as session:
        yield session


@pytest.fixture
def client(test_sessionmaker):
    """A fake browser that talks to the app using the temporary database."""
    from app.main import app
    from app.services.reports import rate_limiter

    def get_test_db():
        with test_sessionmaker() as session:
            yield session

    app.dependency_overrides[app_db.get_db] = get_test_db
    rate_limiter.reset()  # every test starts with a clean rate limit
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
