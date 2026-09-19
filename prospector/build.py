"""Assemble data/targets.csv from the cached Ad Library pulls."""

from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import pathlib
import re

from .brands import candidates, categories, _norm, _titleize
from .score import fatigue_score, segment

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "targets.csv"

COLUMNS = [
    "brand", "website", "category", "segment", "ad_count", "ugc_ad_count_est",
    "oldest_ad_days", "newest_ad_days", "fatigue_score", "notes",
]


def _days_since(ts: int | None, today: dt.date) -> int | None:
    if not ts:
        return None
    return (today - dt.datetime.utcfromtimestamp(ts).date()).days


def _prev_counts(today: dt.date) -> dict[str, int]:
    """Ad counts from the newest snapshot at least 21 days old -- the month-over-month baseline."""
    best, best_age = {}, None
    for f in sorted(glob.glob(str(RAW / "snapshots" / "*.json"))):
        stamp = pathlib.Path(f).stem
        try:
            age = (today - dt.date.fromisoformat(stamp)).days
        except ValueError:
            continue
        if age >= 21 and (best_age is None or age < best_age):
            best, best_age = json.load(open(f)), age
    return best


def build(today: dt.date | None = None) -> list[dict]:
    today = today or dt.date.today()
    disc = {pathlib.Path(f).stem: json.load(open(f))
            for f in glob.glob(str(RAW / "discovery" / "*.json"))}
    meas = json.load(open(RAW / "advertisers" / "measurements.json"))
    prev = _prev_counts(today)
    cats = categories()

    rows = []
    for c in candidates(disc):
        m = meas.get(c["page_id"])
        if not m:
            continue

        ad_count = int(re.sub(r"[^\d]", "", m["ad_count_text"] or "0") or 0)
        sampled, sampled_v = m["sampled"], m["sampled_video"]
        complete = sampled > 0 and ad_count <= sampled

        notes = []
        if complete or sampled == 0:
            ugc = sampled_v
        else:
            # Only the first ~30 cards render, so scale the sample's video share to the full count.
            ugc = round(ad_count * sampled_v / sampled)
            notes.append(f"ugc est. from {sampled}-ad sample")

        oldest = _days_since(m["oldest_start"], today)
        newest = _days_since(m["newest_start"], today)
        if not complete and sampled:
            notes.append("ad ages from sample; true oldest may be older")

        prev_n = prev.get(c["page_id"])
        if prev_n and prev_n > ad_count:
            notes.append(f"ad count {prev_n}->{ad_count} MoM")

        score = fatigue_score(ad_count, ugc, oldest, newest, prev_n)
        seg = segment(ad_count, ugc, newest)

        # Prefer the page name when it looks like the brand; otherwise name the brand after its site.
        dom_stem = _norm(c["website"].split(".")[0]) if c["website"] else ""
        pname = c["brand"]
        looks_like = dom_stem and (_norm(pname) in dom_stem or dom_stem in _norm(pname))
        # The destination domain is the verifiable identity -- a page name only wins when it
        # matches that domain, because affiliates advertise under names of their own.
        own_name = looks_like or not c["website"]
        brand = pname if own_name else _titleize(c["website"])
        if not own_name:
            notes.append(f"advertises as \"{pname}\"")
        if c["affiliate_pages"]:
            notes.append(f"{c['affiliate_pages']} affiliate page(s) run its creative")
        cat = cats.get(c["website"], "unverified")
        if cat not in ("skincare", "unverified"):
            notes.append(f"{cat} — EXCLUDE from skincare hook corpus (DESIGN.md §4)")
        if ugc >= 15:
            notes.append("15+ UGC video ads")
        if seg == "dormant":
            notes.append(f"dormant -- nothing new in {newest}d, exclude from outreach")
        elif newest is not None and newest >= 60:
            notes.append(f"nothing new in {newest}d")

        rows.append({
            "brand": brand,
            "website": f"https://{c['website']}" if c["website"] else "",
            "category": cats.get(c["website"], "unverified"),
            "segment": seg,
            "ad_count": ad_count,
            "ugc_ad_count_est": ugc,
            "oldest_ad_days": oldest if oldest is not None else "",
            "newest_ad_days": newest if newest is not None else "",
            "fatigue_score": score,
            "notes": "; ".join(notes),
            "_page_id": c["page_id"],
        })

    rows.sort(key=lambda r: -r["fatigue_score"])

    # Snapshot this run's counts so the next run can compute the month-over-month decline signal.
    (RAW / "snapshots").mkdir(parents=True, exist_ok=True)
    (RAW / "snapshots" / f"{today.isoformat()}.json").write_text(
        json.dumps({r["_page_id"]: r["ad_count"] for r in rows}, indent=2))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return rows
