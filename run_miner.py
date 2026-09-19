#!/usr/bin/env python3
"""Agent 1 (Ad miner) driver.

Stage 1  plan   -- resolve the mining scope and emit the collection plan. Offline, free.
Stage 2  build  -- normalise a completed pull into hooks.jsonl. Offline, free.

Stage 2 is inert until an approved data source has written per-ad records (including the
transcribed opening) into data/raw/ads/. See docs/DESIGN.md §10 and shared/STATUS.md.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from miner import adlibrary, hooks as hooks_mod
from miner.targets import resolve

ROOT = pathlib.Path(__file__).resolve().parent
SHARED = pathlib.Path.home() / "Desktop" / "ai-ugc-system" / "shared" / "data"
ADS = ROOT / "data" / "raw" / "ads"

# Approved 2026-09-19: ship copy-derived openings, labelled, pending a transcript source (§10).
ALLOW_COPY_DERIVED = True


def plan() -> pathlib.Path:
    rows = resolve()
    payload = [{
        "brand": t["brand"],
        "page_id": t["page_id"],
        "segment": t["segment"],
        "est_video_ads": t["ugc_ad_count_est"],
        "url": adlibrary.advertiser_url(t["page_id"]),
        "collected": adlibrary.is_cached(t["page_id"]),
    } for t in rows]
    out = ROOT / "data" / "raw" / "agent1_collection_plan.json"
    out.write_text(json.dumps(payload, indent=2))
    done = sum(p["collected"] for p in payload)
    print(f"plan: {len(payload)} advertisers in scope, {done} collected, {len(payload)-done} outstanding")
    print(f"  -> {out}")
    return out


def build() -> None:
    files = sorted(ADS.glob("*.json")) if ADS.exists() else []
    if not files:
        print("build: no per-ad pulls in data/raw/ads/ — nothing to normalise.")
        print("       Agent 1 is BLOCKED on the docs/DESIGN.md §10 data-source decision.")
        return
    by_page = {t["page_id"]: t["brand"] for t in resolve()}
    records = []
    for f in files:
        for a in json.loads(f.read_text()):
            records.append(hooks_mod.AdRecord(
                brand=by_page.get(a.get("page_id"), a.get("page_name", "?")),
                ad_id=a["ad_id"], start_date=a.get("start_date"), end_date=a.get("end_date"),
                is_active=a.get("is_active", True), display_format=a.get("display_format"),
                has_video=a.get("has_video", False), primary_text=a.get("primary_text"),
                hook_text=a.get("hook_text"),
            ))
    h, p = hooks_mod.build(records, allow_copy_derived=ALLOW_COPY_DERIVED)
    hooks_mod.write_jsonl(h, SHARED / "hooks.jsonl")
    hooks_mod.write_jsonl(p, ROOT / "data" / "hooks_pending.jsonl")
    print(f"build: {len(records)} ads -> {len(h)} hooks (30d+), {len(p)} pending")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    {"plan": plan, "build": build}[cmd]()
