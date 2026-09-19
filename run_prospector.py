#!/usr/bin/env python3
"""Agent -1 (Prospector) -- rebuild data/targets.csv from the cached Ad Library pulls.

    python3 run_prospector.py              # rebuild the CSV from data/raw/ (offline)
    python3 run_prospector.py --plan       # print the URLs a browser operator should re-open

Collection itself is a supervised browsing step, not an unattended crawl -- see
prospector/adlibrary.py for why.
"""

import sys

from prospector import adlibrary
from prospector.build import build


def main() -> int:
    if "--plan" in sys.argv:
        print("# Discovery -- harvest advertisers (run adlibrary.EXTRACT_JS on each)")
        for q in adlibrary.SEED_QUERIES:
            print(adlibrary.search_url(q, media_type="video"))
        print("\n# Per-advertiser measurement")
        import json, pathlib
        p = pathlib.Path("data/raw/candidates.json")
        if p.exists():
            for c in json.loads(p.read_text()):
                print(adlibrary.advertiser_url(c["page_id"]))
        return 0

    rows = build()
    scored = [r for r in rows if r["fatigue_score"] > 0]
    print(f"wrote data/targets.csv -- {len(rows)} brands ({len(scored)} scoring above zero)")
    for r in rows[:10]:
        print(f"  {r['fatigue_score']:5.1f}  {r['brand'][:26]:28} "
              f"ads={r['ad_count']:<5} ugc={r['ugc_ad_count']:<5} newest={r['newest_ad_days']}d")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
