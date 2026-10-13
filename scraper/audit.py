"""Write a data-audit report to the workspace output/ folder.

    .venv\\Scripts\\python -m scraper.audit

It only READS data/maple.db (no network at all). The checks themselves live in
app/services/audit.py (the same ones the /audit web page shows). This script
just turns them into a short Markdown file:
    <workspace>/output/data-audit-YYYY-MM-DD.md

Tip: run `python -m scraper.run` first so the "Sources disagree" check
(the audit_findings table) is up to date.
"""
from collections import Counter
from datetime import date
from pathlib import Path

from app.db import SessionLocal
from app.services import audit

# maple-classic-db/scraper/audit.py -> parents[2] is the workspace ("First Agent")
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"
TOP_N = 10  # how many example issues to list per check


def describe(row: dict) -> str:
    """One readable line for any audit row (rows from different checks have different keys)."""
    if row.get("detail"):  # "Sources disagree" rows come with a ready-made sentence
        npc = row.get("npc")
        return f"{npc['name']}: {row['detail']}" if npc and npc.get("name") else row["detail"]
    parts = []
    if row.get("monster"):
        parts.append(f"{row['monster']['name']} (mob {row['monster']['id']})")
    if row.get("item"):
        parts.append(f"{row['item']['name']} (item {row['item']['id']})")
    line = " drops ".join(parts) if row.get("monster") and row.get("item") else ", ".join(parts)
    if row.get("rate_label"):
        line += f", listed rate {row['rate_label']}"
    observed = row.get("observed") or {}
    if observed.get("label"):
        line += f", player reports: {observed['label']}"
    return line or str(row)


def build_report(db) -> str:
    """The whole report as Markdown text."""
    counts = audit.summary(db)
    lines = [
        f"# Data audit, {date.today().isoformat()}",
        "",
        f"- Data last loaded: {audit.last_run(db) or 'unknown'}",
        "- Made by `python -m scraper.audit`. Same checks as the site's /audit page.",
        "",
        "## Counts",
    ]
    lines += [f"- {c['label']}: **{counts[c['slug']]}**" for c in audit.CHECKS]

    for c in audit.CHECKS:
        rows, count = audit.run_check(db, c["slug"], limit=None)
        lines += ["", f"## {c['label']} ({count})", f"_{c['description']}_", ""]
        if not rows:
            lines.append("- None found.")
            continue
        kinds = Counter(r["kind"] for r in rows if r.get("kind"))
        if kinds:  # break "Sources disagree" down by type of finding
            lines.append("- By type: " + ", ".join(f"{k} {n}" for k, n in kinds.most_common()))
        for row in rows[:TOP_N]:
            lines.append(f"- {describe(row)}")
        if count > TOP_N:
            lines.append(f"- ...and {count - TOP_N} more (see /audit?check={c['slug']})")

    lines += [
        "",
        "## Sources",
        "- OSMS Data Explorer (game client datamine): https://osmsdataexplorer.com/ "
        "(local copy in maple-classic-db/data/raw/osms/)",
        "- MapleStory Quest (drop tables, NPC shops; read from the local page cache, no new requests): "
        "https://maplestory.quest/",
        "- Player reports submitted on this site (drop_reports table)",
        "- Hand-checked fixes: maple-classic-db/scraper/corrections.py",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_file = OUTPUT_DIR / f"data-audit-{date.today().isoformat()}.md"
    with SessionLocal() as db:
        out_file.write_text(build_report(db), encoding="utf-8")
        counts = audit.summary(db)
    print(f"Wrote {out_file}")
    for slug, n in counts.items():
        print(f"  {slug:<20} {n}")


if __name__ == "__main__":
    main()
