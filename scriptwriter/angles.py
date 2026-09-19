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

# Miner's hooks.jsonl carries hook_source per row: a verbatim transcribed opening, or the opening
# of the ad's primary text. They are not the same artifact. An angle clustered from copy openings
# describes a CLAIM space ("the only filtered showerhead with 2.5x pressure"); an angle clustered
# from transcribed openings describes a HOOK space ("I stopped washing my hair in tap water").
# Agent 3 has to know which it is, because a copy-derived angle must not be echoed as if its
# language were a proven opening line.
TRANSCRIBED = "transcribed"
COPY_DERIVED = "ad_copy_opening"


def evidence_grade(angle: dict) -> str:
    """Return transcribed | copy_derived | mixed | unknown for one angle.

    Accepts either a `hook_sources` count map ({transcribed: 4, ad_copy_opening: 1}) or a plain
    list of source labels, so it survives whichever shape Agent 2 emits.
    """
    src = angle.get("hook_sources")
    if not src:
        return "unknown"
    if isinstance(src, dict):
        present = {k for k, v in src.items() if v}
    else:
        present = set(src)
    has_t, has_c = TRANSCRIBED in present, COPY_DERIVED in present
    if has_t and has_c:
        return "mixed"
    if has_t:
        return "transcribed"
    if has_c:
        return "copy_derived"
    return "unknown"


# How much an angle's own wording can be leaned on, by grade.
EVIDENCE_NOTE = {
    "transcribed": (
        "Clustered from VERBATIM TRANSCRIBED ad openings. The angle reflects how real hooks are "
        "actually spoken, so its shape is evidence — follow it closely."
    ),
    "copy_derived": (
        "Clustered from AD PRIMARY TEXT openings, not spoken hooks. This describes a CLAIM pattern, "
        "not a proven opening line. Use it for WHAT the angle argues, never for HOW it is phrased — "
        "write the spoken hook fresh, and do not echo claim-block cadence "
        "(\"the only...\", \"clinically proven...\", spec lists)."
    ),
    "mixed": (
        "Clustered from a mix of transcribed openings and ad copy openings. Treat the transcribed "
        "share as the guide for phrasing; treat the rest as argument only."
    ),
    "unknown": (
        "Provenance of the underlying hooks is not recorded. Treat as claim-level evidence only and "
        "write the spoken hook fresh."
    ),
}


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
