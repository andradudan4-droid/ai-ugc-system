#!/usr/bin/env python3
"""Fail if any disqualified brand has reappeared in targets.csv.

`run_prospector.py` rebuilds from data/raw/, which holds ad-behaviour data only. Disqualification
is a human judgement made by visiting the site -- Dustri Co. sells hoodies, Emuaid is a regulated
medicinal ointment -- and ad behaviour structurally cannot see it. So a naive rebuild restores
brands that were removed for good reason.

This fails CLOSED and LOUDLY. A gate that fails open is silent; this bug class has been found four
times in this codebase and each time it was caught because something failed noisily.
"""

import csv
import json
import pathlib
import sys


def main() -> int:
    dq_path = pathlib.Path("shared/data/disqualified.json")
    tgt_path = pathlib.Path("data/targets.csv")
    if not dq_path.exists() or not tgt_path.exists():
        print("BLOCKED: disqualified.json or targets.csv missing — refusing to pass", file=sys.stderr)
        return 1  # missing input blocks, it does not pass

    raw = json.loads(dq_path.read_text())
    entries = raw if isinstance(raw, list) else list(raw)
    domains = {str(d).strip().lower() for d in entries if not str(d).startswith("_")}
    if not domains:
        print("BLOCKED: disqualified list parsed empty — refusing to pass", file=sys.stderr)
        return 1

    offenders = []
    with tgt_path.open() as fh:
        for row in csv.DictReader(fh):
            site = (row.get("website") or "").lower()
            for d in domains:
                if d and d in site:
                    offenders.append((row.get("brand", "?"), d, row.get("segment", "?")))
                    break

    if offenders:
        print("DISQUALIFIED BRANDS REAPPEARED IN targets.csv:", file=sys.stderr)
        for brand, domain, seg in offenders:
            print(f"  - {brand} ({domain}) — ranked '{seg}'", file=sys.stderr)
        print("\nThe rebuild restores brands removed by human judgement. Fix the filter in "
              "prospector/build.py before this list is used for outreach.", file=sys.stderr)
        return 1

    print(f"OK — {len(domains)} disqualified brands, none present in targets.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
