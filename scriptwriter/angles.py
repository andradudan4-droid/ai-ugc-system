"""Load angles.json (Agent 2's output) and refuse to let fixture data escape.

Agent 2 is owned by Miner and angles.json does not exist yet, so Agent 3 is built against a
fixture. The fixture is hand-written, which means it is category-plausible but not evidence --
clustering it would produce invented "unclaimed angles", and that is the thing we sell to a brand.
So a fixture is marked `_fixture: true` at the top level, every script generated from it is stamped
FIXTURE in `provenance`, and publishing is refused. Swapping in Miner's real file removes the
marker and the guard stops firing -- no code change.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARED = pathlib.Path.home() / "Desktop" / "ai-ugc-system" / "shared" / "data"
FIXTURE = ROOT / "data" / "fixtures" / "angles.fixture.json"

REQUIRED_ANGLE = ["angle_id", "label", "description", "hook_ids"]


class FixtureData(Exception):
    """Raised when fixture-derived output would reach a client-facing location."""


def source_path() -> pathlib.Path:
    """Prefer Miner's real artifact; fall back to the fixture so Agent 3 stays testable."""
    real = SHARED / "angles.json"
    return real if real.exists() else FIXTURE


def load() -> tuple[list[dict], bool, pathlib.Path]:
    """Return (angles, is_fixture, path)."""
    p = source_path()
    if not p.exists():
        raise SystemExit(f"no angles source at {p}")
    doc = json.loads(p.read_text())
    is_fixture = bool(doc.get("_fixture"))
    angles = doc.get("angles", [])

    for i, a in enumerate(angles):
        missing = [f for f in REQUIRED_ANGLE if f not in a]
        if missing:
            raise SystemExit(f"angle[{i}] missing {missing} in {p}")
    return angles, is_fixture, p


def guard_publish(is_fixture: bool) -> None:
    if is_fixture:
        raise FixtureData(
            "angles source is a FIXTURE — hand-written, not mined from real ads. "
            "Refusing to publish to shared/data/. Wire in Miner's angles.json first."
        )
