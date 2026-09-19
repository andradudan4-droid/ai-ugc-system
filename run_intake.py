#!/usr/bin/env python3
"""Agent 0 (Intake) -- render data/brands/<slug>/brand.md from cached brand-site pulls.

    python3 run_intake.py                  # render every cached brand
    python3 run_intake.py --plan --top 5   # print the URLs to open for the top 5 fatigued targets
"""

import csv
import pathlib
import sys

from intake import sites
from intake.render import render


def top_fatigued(n: int) -> list[tuple[str, str]]:
    rows = [r for r in csv.DictReader(open("data/targets.csv")) if r["segment"] == "fatigued"]
    rows.sort(key=lambda r: -float(r["fatigue_score"]))
    return [(r["brand"], r["website"].replace("https://", "").rstrip("/")) for r in rows[:n]]


def main() -> int:
    if "--plan" in sys.argv:
        n = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 5
        for brand, dom in top_fatigued(n):
            print(f"# {brand}")
            print(sites.products_url(dom))
            print(sites.home_url(dom))
        return 0

    doms = sites.cached_domains()
    if not doms:
        print("no cached pulls in data/raw/intake/ -- run with --plan first")
        return 1
    for d in doms:
        p = render(d)
        print(f"wrote {p.relative_to(pathlib.Path.cwd())} ({p.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
