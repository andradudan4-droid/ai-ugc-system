"""Resolve the Agent 1 mining scope: targets.csv rows -> Ad Library page_ids.

Pure local computation over artifacts already on disk. No network.
"""

from __future__ import annotations

import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARED = pathlib.Path.home() / "Desktop" / "ai-ugc-system" / "shared" / "data"
CANDIDATES = ROOT / "data" / "raw" / "candidates.json"

# docs/DESIGN.md §3: Agent 1 mines the competitor set. Per the build brief that is every
# advertiser still buying — fatigued (our prospects), high_volume and active (the ones whose
# creative actually defines the category).
IN_SCOPE = {"fatigued", "high_volume", "active"}


def _norm(domain: str) -> str:
    d = (domain or "").strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p):
            d = d[len(p):]
    return d.strip("/").removeprefix("www.")


def resolve(targets_csv: pathlib.Path | None = None) -> list[dict]:
    """Every in-scope brand joined to the page_id Agent -1 already discovered."""
    targets_csv = targets_csv or (SHARED / "targets.csv")
    by_domain = {_norm(c["website"]): c for c in json.loads(CANDIDATES.read_text())}

    out, unresolved = [], []
    for row in csv.DictReader(targets_csv.open()):
        if row["segment"] not in IN_SCOPE:
            continue
        cand = by_domain.get(_norm(row["website"]))
        if not cand:
            unresolved.append(row["brand"])
            continue
        out.append({
            "brand": row["brand"],
            "website": _norm(row["website"]),
            "segment": row["segment"],
            "page_id": cand["page_id"],
            "ad_count": int(row["ad_count"]),
            "ugc_ad_count_est": int(row["ugc_ad_count_est"]),
        })
    if unresolved:
        raise LookupError(f"no page_id for: {unresolved}")
    return out
