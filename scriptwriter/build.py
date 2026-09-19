"""Emit Agent 3 prompts and assemble returned scripts into scripts.json."""

from __future__ import annotations

import json
import pathlib
import re

from .angles import FixtureData, evidence_grade, guard_publish, load
from .prompt import build as build_prompt
from .schema import validate

# A thin corpus does not make a script wrong, it makes it unproven. Agent 2's pilot ran 4 brands
# (effectively 3 -- SpoiledChild contributes 2 hooks after the off-category gate), and contamination
# in that pilot already inverted one result: customer_testimonial read as the most saturated angle
# in the category off 25 ads, but 24 were ingestible or body-care. In facial skincare it runs on
# one. An "unclaimed" angle measured against 3 brands carries the same risk in the other direction.
# So client-readiness is a gate on the CORPUS, checked mechanically, not a judgement call per batch.
CLIENT_READY_MIN_BRANDS = 8
CLIENT_READY_MIN_HOOKS = 150

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


def client_readiness(corpus: dict, is_fixture: bool) -> tuple[bool, str]:
    """Is the angle evidence strong enough to put derived scripts in front of a brand?"""
    if is_fixture:
        return False, "Generated from a hand-written FIXTURE. Not real evidence."
    brands, hooks = len(corpus.get("brands", [])), corpus.get("hooks", 0)
    if brands < CLIENT_READY_MIN_BRANDS or hooks < CLIENT_READY_MIN_HOOKS:
        return False, (
            f"PIPELINE TEST — angle corpus is {hooks} hooks from {brands} brands, below the "
            f"{CLIENT_READY_MIN_HOOKS}/{CLIENT_READY_MIN_BRANDS} bar for client-facing work. "
            "Contamination in a pilot this size already inverted one angle result once. Nothing "
            "here goes near a brand until Agent 2 re-derives on the extended corpus and reports "
            "which angles survive."
        )
    return True, f"Angle corpus is {hooks} hooks from {brands} brands."


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

    ready, ready_why = client_readiness(corpus, is_fixture)
    scripts, problems = [], []
    for f in sorted(RETURNS.glob("*.json")):
        slug, angle_id = f.stem.split("--", 1)
        prompt_f = PROMPTS / f"{slug}--{angle_id}.json"
        banned = json.loads(prompt_f.read_text())["do_not_say"] if prompt_f.exists() else []

        for s in json.loads(f.read_text()):
            # Provenance is stamped from the angles file, not taken from the model's output.
            a = by_id.get(s.get("angle_id") or angle_id)
            if not a:
                # Agent 2 re-derives on new corpora and angles appear and vanish between versions.
                # A script whose angle no longer exists has lost its evidentiary basis and cannot be
                # re-validated -- reject it. Never default a missing angle to "unclaimed": that is a
                # positive claim of verified absence, and it would turn a stale reference into the
                # most sellable label in the set.
                problems.append({
                    "file": f.name, "script_id": s.get("script_id"),
                    "errors": [f"angle_id '{s.get('angle_id')}' is not in {src.name} — the angle it "
                               f"was written against no longer exists in the corpus. Rewrite "
                               f"against a current angle."],
                })
                continue
            s["angle_evidence"] = evidence_grade(a)
            s["angle_saturation"] = a.get("saturation", "unclaimed")
            s["source_hook_ids"] = a.get("hook_ids", [])
            s["attribution_basis"] = _attribution(a, s["angle_evidence"])
            s["client_ready"] = ready
            if not ready:
                s["hold_reason"] = ready_why
            elif s["angle_saturation"] == "unclaimed":
                s["client_ready"] = False
                s["hold_reason"] = (
                    "Angle is UNCLAIMED — established by absence. Absence is only as strong as the "
                    "corpus it was measured against; confirm against the extended corpus first."
                )
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
        "client_ready": ready,
        "client_ready_reason": ready_why,
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
