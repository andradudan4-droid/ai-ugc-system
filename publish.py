#!/usr/bin/env python3
"""Copy finished artifacts into the shared tree other sessions read (see ROLES.md).

Code stays per-session in a worktree; data is shared. Artifacts are produced in the worktree so
they are under version control, then mirrored here by absolute path.
"""

import pathlib
import shutil

SHARED = pathlib.Path.home() / "Desktop" / "ai-ugc-system" / "shared" / "data"
LOCAL = pathlib.Path(__file__).resolve().parent / "data"


def publish() -> list[str]:
    SHARED.mkdir(parents=True, exist_ok=True)
    done = []

    for name in ("targets.csv", "disqualified.json"):
        src = LOCAL / name
        if src.exists():
            shutil.copy2(src, SHARED / name)
            done.append(name)

    brands = LOCAL / "brands"
    if brands.exists():
        for bm in sorted(brands.glob("*/brand.md")):
            dst = SHARED / "brands" / bm.parent.name / "brand.md"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bm, dst)
            done.append(f"brands/{bm.parent.name}/brand.md")
    return done


if __name__ == "__main__":
    for f in publish():
        print(f"published -> {SHARED}/{f}")
