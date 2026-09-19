#!/usr/bin/env python3
"""Agent 3 (Scriptwriter) — docs/DESIGN.md §3.

    python3 run_scriptwriter.py --emit <brand_slug> [--angles A01,A03] [--n 3]
    python3 run_scriptwriter.py --assemble

Phase B (docs/DESIGN.md §6): --emit writes one prompt file per angle. Run each prompt, save the
returned JSON array to data/scripts/returns/<slug>--<angle_id>.json, then --assemble validates and
builds scripts.json. Phase A swaps the manual step for an API call against the same prompts.
"""

import json
import sys

from scriptwriter.build import assemble, emit_prompts


def main() -> int:
    if "--emit" in sys.argv:
        slug = sys.argv[sys.argv.index("--emit") + 1]
        ids = None
        if "--angles" in sys.argv:
            ids = sys.argv[sys.argv.index("--angles") + 1].split(",")
        n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 3
        files = emit_prompts(slug, ids, n)
        print(f"wrote {len(files)} prompt(s) for {slug}:")
        for f in files:
            print(f"  {f}")
        return 0

    if "--assemble" in sys.argv:
        doc = assemble()
        print(f"scripts.json — {doc['script_count']} valid, {len(doc['rejected'])} rejected")
        for p in doc["rejected"]:
            print(f"  REJECTED {p['script_id']}: {'; '.join(p['errors'])}")
        print("published to shared/data/" if doc["published"]
              else f"NOT published — {doc['publish_refused']}")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
