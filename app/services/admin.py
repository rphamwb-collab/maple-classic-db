"""The admin page (GET /admin): see recent player reports and delete bad ones.

Login is a browser password box (HTTP Basic). The password comes from the
ADMIN_PASSWORD environment variable; if it isn't set, the admin page is off
(every /admin URL answers 404), so a fresh install is never left open.
"""

import base64
import os
import secrets

from sqlalchemy import select

from app.models import DropReport, Item, Monster, PriceReport

ADMIN_USER = "admin"
RECENT_LIMIT = 200  # newest reports shown per table


def admin_password():
    return os.environ.get("ADMIN_PASSWORD", "")


def check_login(authorization):
    """True if the Authorization header holds admin:<ADMIN_PASSWORD>."""
    password = admin_password()
    if not password or not (authorization or "").startswith("Basic "):
        return False
    try:
        user, _, given = base64.b64decode(authorization[6:]).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    # compare_digest takes the same time whether the guess is close or not.
    return secrets.compare_digest(user, ADMIN_USER) & secrets.compare_digest(given, password)


def same_site(origin, referer, host):
    """Delete buttons must be clicked on our own site. Browsers send the saved
    password with every request, so this stops another site from posting here."""
    source = origin or referer or ""
    return source.split("://", 1)[-1].split("/", 1)[0] == host


def recent_reports(db):
    """Newest price and drop reports, with item / monster names for the table."""
    names = dict(db.execute(select(Item.id, Item.name)).all())
    monsters = dict(db.execute(select(Monster.id, Monster.name)).all())
    prices = db.scalars(select(PriceReport).order_by(PriceReport.id.desc()).limit(RECENT_LIMIT)).all()
    drops = db.scalars(select(DropReport).order_by(DropReport.id.desc()).limit(RECENT_LIMIT)).all()
    return {
        "prices": [{"id": r.id, "item_id": r.item_id, "item": names.get(r.item_id, r.item_id),
                    "price": r.price, "quantity": r.quantity, "world": r.world,
                    "reported_at": r.reported_at, "ip": r.reporter_ip} for r in prices],
        "drops": [{"id": r.id, "monster_id": r.monster_id, "monster": monsters.get(r.monster_id, r.monster_id),
                   "item_id": r.item_id, "item": names.get(r.item_id, r.item_id), "kills": r.kills,
                   "drops": r.drops_seen, "world": r.world, "reported_at": r.reported_at,
                   "ip": r.reporter_ip} for r in drops],
    }


def delete_report(db, kind, report_id):
    """Delete one report. kind is "prices" or "drops". Returns True if it existed."""
    model = {"prices": PriceReport, "drops": DropReport}[kind]
    report = db.get(model, report_id)
    if report is None:
        return False
    db.delete(report)
    db.commit()
    return True
