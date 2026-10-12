"""Tests for the admin page (GET /admin) that deletes bad player reports."""

from sqlalchemy import select

from app.models import Drop, DropReport, Item, PriceReport

PASSWORD = "test-password"
SAME_SITE = {"Origin": "http://testserver"}


def make_price_report(db):
    item_id = db.scalar(select(Item.id))
    report = PriceReport(item_id=item_id, price=999_999, quantity=1, world="Scania", reporter_ip="1.2.3.4")
    db.add(report)
    db.commit()
    return report.id


def test_admin_is_off_without_a_password(client, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert client.get("/admin").status_code == 404


def test_admin_asks_for_the_password(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    r = client.get("/admin")
    assert r.status_code == 401 and "Basic" in r.headers["WWW-Authenticate"]
    assert client.get("/admin", auth=("admin", "wrong")).status_code == 401


def test_admin_lists_and_deletes_reports(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    report_id = make_price_report(db)
    page = client.get("/admin", auth=("admin", PASSWORD))
    assert page.status_code == 200 and f"/admin/prices/{report_id}/delete" in page.text

    r = client.post(f"/admin/prices/{report_id}/delete", auth=("admin", PASSWORD),
                    headers=SAME_SITE, follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert db.get(PriceReport, report_id) is None


def test_admin_delete_needs_login_and_same_site(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    report_id = make_price_report(db)
    # Not logged in.
    assert client.post(f"/admin/prices/{report_id}/delete", headers=SAME_SITE).status_code == 401
    # Logged in, but the click came from another website.
    r = client.post(f"/admin/prices/{report_id}/delete", auth=("admin", PASSWORD),
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    db.expire_all()
    assert db.get(PriceReport, report_id) is not None


def test_admin_deletes_drop_reports(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    drop = db.scalars(select(Drop)).first()
    report = DropReport(monster_id=drop.monster_id, item_id=drop.item_id, kills=10, drops_seen=1,
                        world="Scania", reporter_ip="1.2.3.4")
    db.add(report)
    db.commit()
    report_id = report.id
    r = client.post(f"/admin/drops/{report_id}/delete", auth=("admin", PASSWORD),
                    headers={**SAME_SITE, "HX-Request": "true"})
    assert r.status_code == 200 and r.text == ""
    db.expire_all()
    assert db.get(DropReport, report_id) is None
