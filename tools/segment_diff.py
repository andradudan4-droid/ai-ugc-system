#!/usr/bin/env python3
"""Compare two targets.csv snapshots and report what moved.

    python3 tools/segment_diff.py before.csv data/targets.csv

Ad ages recompute from stored dates on every run, so brands drift between segments purely
with the passage of time -- a brand silent for 44 days is `active`, at 45 it enters the
fatigue window and becomes worth pitching. That drift is the point: it surfaces new leads
without collecting anything new.

Exit 0 always. Prints a markdown report to stdout, or nothing if nothing moved.
"""

import csv
import pathlib
import sys

# Segments worth waking someone up for, in priority order.
URGENT = ("fatigued", "cooling")


def load(path: str) -> dict[str, dict]:
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    with p.open() as fh:
        return {r["brand"]: r for r in csv.DictReader(fh) if r.get("brand")}


def main() -> int:
    before, after = load(sys.argv[1]), load(sys.argv[2])
    if not after:
        print("ERROR: new targets.csv is empty or missing", file=sys.stderr)
        return 0

    entered, left, moved, new = [], [], [], []
    for brand, row in after.items():
        old = before.get(brand)
        seg = row.get("segment", "?")
        if old is None:
            if seg in URGENT:
                new.append((brand, seg, row))
            continue
        was = old.get("segment", "?")
        if was == seg:
            continue
        if seg in URGENT and was not in URGENT:
            entered.append((brand, was, seg, row))
        elif was in URGENT and seg not in URGENT:
            left.append((brand, was, seg, row))
        else:
            moved.append((brand, was, seg, row))

    if not (entered or left or moved or new):
        return 0  # silence is the correct output when nothing changed

    out = []
    if entered or new:
        out.append("## New leads\n")
        out.append("Brands that entered the fatigue window — still advertising, but shipping nothing new.\n")
        out.append("| Brand | Was | Now | Ads | UGC | Days silent | Score |")
        out.append("|---|---|---|---|---|---|---|")
        for brand, was, seg, r in sorted(entered, key=lambda x: -float(x[3].get("fatigue_score") or 0)):
            out.append(f"| {brand} | {was} | **{seg}** | {r.get('ad_count','')} | "
                       f"{r.get('ugc_ad_count_est','')} | {r.get('newest_ad_days','')}d | "
                       f"{r.get('fatigue_score','')} |")
        for brand, seg, r in new:
            out.append(f"| {brand} | _new_ | **{seg}** | {r.get('ad_count','')} | "
                       f"{r.get('ugc_ad_count_est','')} | {r.get('newest_ad_days','')}d | "
                       f"{r.get('fatigue_score','')} |")
        out.append("")

    if left:
        out.append("## Dropped out\n")
        for brand, was, seg, r in left:
            note = " — gone quiet, likely stopped advertising" if seg == "dormant" else ""
            out.append(f"- **{brand}**: {was} → {seg}{note}")
        out.append("")

    if moved:
        out.append("## Other movement\n")
        for brand, was, seg, _ in moved:
            out.append(f"- {brand}: {was} → {seg}")
        out.append("")

    out.append("---")
    out.append("_Re-scored from cached data. No new collection, no spend. "
               "Ages recompute daily, so this is drift, not fresh mining._")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
