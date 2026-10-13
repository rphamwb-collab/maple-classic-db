"""A data refresh (scraper.run) must never delete what players reported.

We build a small throwaway database, add a price report and a drop report,
run rebuild_tables() on it, and check both reports are still there while the
game-data tables (items, audit_findings, ...) were emptied.
This uses its OWN temp database, so it never touches data/maple.db.
"""
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models import AuditFinding, Base, DropReport, Item, Monster, PriceReport, Source
from scraper.run import KEEP_TABLES, rebuild_tables


def make_temp_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'rebuild.db').as_posix()}")
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine)


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_rebuild_keeps_player_reports(tmp_path):
    engine, Session = make_temp_db(tmp_path)
    with Session() as db:
        db.add(Source(id=1, name="test"))
        db.add(Item(id=2000000, name="Red Potion", category="use", jobs=[], source_id=1))
        db.add(Monster(id=100100, name="Snail", source_id=1))
        db.add(AuditFinding(check="name_mismatch", item_id=2000000, detail="test"))
        db.add(PriceReport(item_id=2000000, price=50, world="Scania", reporter_ip="10.0.0.1"))
        db.add(DropReport(monster_id=100100, item_id=2000000, kills=100, drops_seen=4, world="Scania"))
        db.commit()

    rebuild_tables(bind=engine)

    with Session() as db:
        # player reports survived, with their values intact
        assert count(db, PriceReport) == 1
        assert count(db, DropReport) == 1
        assert db.scalar(select(PriceReport.price)) == 50
        assert db.scalar(select(DropReport.drops_seen)) == 4
        # game data (and audit findings) were wiped, ready to be reloaded
        assert count(db, Item) == 0
        assert count(db, Monster) == 0
        assert count(db, AuditFinding) == 0
    engine.dispose()


def test_rebuild_recreates_every_table(tmp_path):
    """After a rebuild, every table exists again (the dropped ones were re-created)."""
    engine, _ = make_temp_db(tmp_path)
    rebuild_tables(bind=engine)
    from sqlalchemy import inspect
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables)
    assert KEEP_TABLES == {"price_reports", "drop_reports"}
    engine.dispose()
