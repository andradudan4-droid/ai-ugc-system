"""Load angles.json (Agent 2's output) and normalise it for Agent 3.

Agent 2 emits angles in four buckets by saturation, not one flat list, and it does NOT carry hook
ids through from hooks.jsonl. Both facts shape what Agent 3 can honestly claim:

- Saturation is the whole point. A saturated angle is where every long-running ad already is, so
  writing there competes with a creative that has survived 600 days. An unclaimed angle is the thing
  actually being sold. The prompt has to know which it is.
- No hook ids means `docs/DESIGN.md` §2 attribution ("every asset traces back to the angle and hook
  that produced it") cannot be completed to hook level. Agent 3 records that gap explicitly rather
  than fabricating ids to satisfy a schema — see `attribution_basis` in schema.py.

A fixture is marked `_fixture: true`, stamps FIXTURE on every script, and cannot publish.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARED = pathlib.Path.home() / "Desktop" / "ai-ugc-system" / "shared" / "data"
FIXTURE = ROOT / "data" / "fixtures" / "angles.fixture.json"

TRANSCRIBED = "transcribed"
COPY_DERIVED = "ad_copy_opening"

SATURATION_BUCKETS = {
    "saturated_angles": "saturated",
    "contested_angles": "contested",
    "single_brand_angles": "single_brand",
    "unclaimed_angles": "unclaimed",
}


class FixtureData(Exception):
    """Raised when fixture-derived output would reach a client-facing location."""


def source_path() -> pathlib.Path:
    real = SHARED / "angles.json"
    return real if real.exists() else FIXTURE


def _humanise(slug: str) -> str:
    return slug.replace("_", " ").strip().capitalize()


def _normalise(doc: dict) -> list[dict]:
    """Flatten Agent 2's saturation buckets into one list Agent 3 can iterate."""
    if "angles" in doc:                     # fixture / flat shape
        return doc["angles"]

    corpus = doc.get("corpus", {})
    out = []
    for key, saturation in SATURATION_BUCKETS.items():
        for a in doc.get(key, []):
            slug = a.get("angle") or a.get("angle_id")
            if not slug:
                continue
            out.append({
                "angle_id": slug,
                "label": _humanise(slug),
                "description": a.get("description") or _describe(a, saturation),
                "saturation": saturation,
                "unclaimed": saturation == "unclaimed",
                "hook_ids": a.get("hook_ids", []),          # Agent 2 does not carry these through
                "hook_sources": a.get("hook_sources") or corpus.get("hook_sources"),
                "hook_type": a.get("hook_type"),
                "brands": a.get("brands", []),
                "ad_count": a.get("ad_count", 0),
                "median_days_running": a.get("median_days_running"),
                "max_days_running": a.get("max_days_running"),
                "examples": a.get("examples", []),
                "probe": a.get("probe"),
                "corpus_hits": a.get("corpus_hits"),
            })
    return out


def _describe(a: dict, saturation: str) -> str:
    brands = ", ".join(a.get("brands", [])) or "unknown brands"
    n, mx = a.get("ad_count", 0), a.get("max_days_running")
    tail = f", longest alive {mx} days" if mx else ""
    return f"{saturation}: {n} ads across {brands}{tail}."


def load() -> tuple[list[dict], bool, pathlib.Path, dict]:
    """Return (angles, is_fixture, path, corpus).

    `corpus` carries Agent 2's version stamps (schema_version, generated_at, corpus_fingerprint) so
    a script can record exactly which corpus it was built against. The fingerprint is a hash over
    the sorted hook ids, so it changes iff the underlying hook set changes.
    """
    p = source_path()
    if not p.exists():
        raise SystemExit(f"no angles source at {p}")
    doc = json.loads(p.read_text())
    angles = _normalise(doc)
    if not angles:
        raise SystemExit(
            f"{p} parsed to zero angles — its shape is not one this loader recognises. "
            f"Top-level keys: {sorted(doc)}. Refusing to run rather than silently produce nothing."
        )
    corpus = dict(doc.get("corpus", {}))
    for k in ("schema_version", "generated_at", "corpus_fingerprint"):
        if k in doc:
            corpus[k] = doc[k]
    return angles, bool(doc.get("_fixture")), p, corpus


def evidence_grade(angle: dict) -> str:
    """transcribed | copy_derived | mixed | unknown. Absent provenance degrades to cautious."""
    src = angle.get("hook_sources")
    if not src:
        return "unknown"
    present = {k for k, v in src.items() if v} if isinstance(src, dict) else set(src)
    has_t, has_c = TRANSCRIBED in present, COPY_DERIVED in present
    if has_t and has_c:
        return "mixed"
    if has_t:
        return "transcribed"
    if has_c:
        return "copy_derived"
    return "unknown"


EVIDENCE_NOTE = {
    "transcribed": (
        "Clustered from VERBATIM TRANSCRIBED ad openings. The angle reflects how real hooks are "
        "actually spoken, so its shape is evidence — follow it closely."
    ),
    "copy_derived": (
        "Clustered from AD PRIMARY TEXT openings, not spoken hooks. This describes a CLAIM pattern, "
        "not a proven opening line. Use it for WHAT the angle argues, never for HOW it is phrased — "
        "write the spoken hook fresh, and do not echo claim-block cadence."
    ),
    "mixed": (
        "Clustered from a mix of transcribed openings and ad copy openings. Treat the transcribed "
        "share as the guide for phrasing; treat the rest as argument only."
    ),
    "unknown": (
        "Provenance of the underlying hooks is NOT recorded in angles.json. Treat as claim-level "
        "evidence only: use the angle for what it argues, write the spoken hook fresh."
    ),
}

SATURATION_NOTE = {
    "saturated": (
        "SATURATED — multiple brands already run this and their ads have survived months. Do not "
        "write here unless the brand has a genuine wedge, and if you do, the execution has to beat "
        "a creative that has been alive for a very long time."
    ),
    "contested": "CONTESTED — more than one brand is present but nothing has run away with it.",
    "single_brand": (
        "SINGLE BRAND — one brand owns this in the sample. If it is this brand's own angle, it is "
        "proven for them and worth extending. If it is a competitor's, entering means a head-on "
        "comparison."
    ),
    "unknown": (
        "UNKNOWN — this angle's competitive position is not recorded. Assume it is contested and "
        "that the position may already be taken; do not write as though it were open."
    ),
    "unclaimed": (
        "UNCLAIMED — zero hits in the mined corpus. This is the angle being sold: nobody in the "
        "sample opens an ad here. There are no example hooks to imitate because none exist, so the "
        "execution is entirely yours to invent from the brand brief."
    ),
}


def guard_publish(is_fixture: bool) -> None:
    if is_fixture:
        raise FixtureData(
            "angles source is a FIXTURE — hand-written, not mined from real ads. "
            "Refusing to publish to shared/data/. Wire in Miner's angles.json first."
        )
