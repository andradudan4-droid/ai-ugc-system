"""Emit Agent 3 prompts and assemble returned scripts into scripts.json."""

from __future__ import annotations

import json
import pathlib
import re

from .angles import FixtureData, evidence_grade, guard_publish, load
from .prompt import build as build_prompt
from .schema import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARED = pathlib.Path.home() / "Desktop" / "ai-ugc-system" / "shared" / "data"
OUT = ROOT / "data" / "scripts"
PROMPTS = OUT / "prompts"
RETURNS = OUT / "returns"


def emit_prompts(slug: str, angle_ids: list[str] | None, n: int) -> list[pathlib.Path]:
    angles, is_fixture, src, corpus = load()
    if angle_ids:
        angles = [a for a in angles if a["angle_id"] in angle_ids]
    prov = f"FIXTURE ({src.name}) — NOT client-safe" if is_fixture else f"angles.json ({src.name})"

    PROMPTS.mkdir(parents=True, exist_ok=True)
    written = []
    for a in angles:
        p = build_prompt(slug, a, n, prov, corpus)
        f = PROMPTS / f"{slug}--{a['angle_id']}.json"
        f.write_text(json.dumps(p, indent=2))
        written.append(f)
    return written


def _attribution(angle: dict | None, grade: str) -> str:
    """State plainly what a script traces back to -- and what it does not."""
    if not angle:
        return "UNTRACEABLE: angle_id not found in the angles source."
    aid, sat = angle["angle_id"], angle.get("saturation")
    if sat == "unclaimed":
        return (
            f"angle={aid} (UNCLAIMED, {angle.get('corpus_hits', 0)} corpus hits). No hooks exist to "
            f"attribute to: the angle is defined by absence, verified by probe regex. Evidence "
            f"grade {grade}. Traceable to the angle only, not to any ad."
        )
    n = angle.get("ad_count", 0)
    brands = ", ".join(angle.get("brands", [])) or "unknown"
    return (
        f"angle={aid} ({sat}, {n} ads across {brands}). Agent 2 does not carry hook ids through "
        f"from hooks.jsonl, so DESIGN.md §2 hook-level attribution is INCOMPLETE — traceable to the "
        f"angle, not to individual ads. Evidence grade {grade}."
    )


def _banned_used(script: dict, banned: list[str]) -> list[str]:
    """Post-check: the model was told the do-not-say list, but verify rather than trust it."""
    spoken = " ".join(
        [script.get("hook", ""), script.get("cta", "")]
        + [b.get("vo", "") for b in script.get("beats", [])]
    ).lower()
    return [b for b in banned if re.search(rf"\b{re.escape(b.lower())}\b", spoken)]


def assemble() -> dict:
    """Read model returns from data/scripts/returns/, validate, write scripts.json."""
    angles, is_fixture, src, corpus = load()
    by_id = {a["angle_id"]: a for a in angles}
    RETURNS.mkdir(parents=True, exist_ok=True)

    scripts, problems = [], []
    for f in sorted(RETURNS.glob("*.json")):
        slug, angle_id = f.stem.split("--", 1)
        prompt_f = PROMPTS / f"{slug}--{angle_id}.json"
        banned = json.loads(prompt_f.read_text())["do_not_say"] if prompt_f.exists() else []

        for s in json.loads(f.read_text()):
            # Provenance is stamped from the angles file, not taken from the model's output.
            a = by_id.get(s.get("angle_id") or angle_id)
            s["angle_evidence"] = evidence_grade(a) if a else "unknown"
            s["angle_saturation"] = (a or {}).get("saturation", "unclaimed")
            s["source_hook_ids"] = (a or {}).get("hook_ids", [])
            s["attribution_basis"] = _attribution(a, s["angle_evidence"])
            errs = validate(s)
            hits = _banned_used(s, banned)
            if hits:
                errs.append(f"uses do-not-say language: {hits}")
            if errs:
                problems.append({"file": f.name, "script_id": s.get("script_id"), "errors": errs})
            else:
                scripts.append(s)

    doc = {
        "generated_from": src.name,
        "corpus": corpus,
        "is_fixture": is_fixture,
        "script_count": len(scripts),
        "rejected": problems,
        "scripts": scripts,
    }
    # Decide publishability BEFORE writing, so the persisted file records its own status --
    # anyone reading scripts.json later must be able to see it came from a fixture.
    try:
        guard_publish(is_fixture)
        doc["published"] = True
        doc["publish_refused"] = None
    except FixtureData as e:
        doc["published"] = False
        doc["publish_refused"] = str(e)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scripts.json").write_text(json.dumps(doc, indent=2))

    if doc["published"]:
        SHARED.mkdir(parents=True, exist_ok=True)
        (SHARED / "scripts.json").write_text(json.dumps(doc, indent=2))
    return doc
