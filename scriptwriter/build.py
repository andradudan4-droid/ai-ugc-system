"""Emit Agent 3 prompts and assemble returned scripts into scripts.json."""

from __future__ import annotations

import json
import pathlib
import re

from .angles import FixtureData, guard_publish, load
from .prompt import build as build_prompt
from .schema import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARED = pathlib.Path.home() / "Desktop" / "ai-ugc-system" / "shared" / "data"
OUT = ROOT / "data" / "scripts"
PROMPTS = OUT / "prompts"
RETURNS = OUT / "returns"


def emit_prompts(slug: str, angle_ids: list[str] | None, n: int) -> list[pathlib.Path]:
    angles, is_fixture, src = load()
    if angle_ids:
        angles = [a for a in angles if a["angle_id"] in angle_ids]
    prov = f"FIXTURE ({src.name}) — NOT client-safe" if is_fixture else f"angles.json ({src.name})"

    PROMPTS.mkdir(parents=True, exist_ok=True)
    written = []
    for a in angles:
        p = build_prompt(slug, a, n, prov)
        f = PROMPTS / f"{slug}--{a['angle_id']}.json"
        f.write_text(json.dumps(p, indent=2))
        written.append(f)
    return written


def _banned_used(script: dict, banned: list[str]) -> list[str]:
    """Post-check: the model was told the do-not-say list, but verify rather than trust it."""
    spoken = " ".join(
        [script.get("hook", ""), script.get("cta", "")]
        + [b.get("vo", "") for b in script.get("beats", [])]
    ).lower()
    return [b for b in banned if re.search(rf"\b{re.escape(b.lower())}\b", spoken)]


def assemble() -> dict:
    """Read model returns from data/scripts/returns/, validate, write scripts.json."""
    _, is_fixture, src = load()
    RETURNS.mkdir(parents=True, exist_ok=True)

    scripts, problems = [], []
    for f in sorted(RETURNS.glob("*.json")):
        slug, angle_id = f.stem.split("--", 1)
        prompt_f = PROMPTS / f"{slug}--{angle_id}.json"
        banned = json.loads(prompt_f.read_text())["do_not_say"] if prompt_f.exists() else []

        for s in json.loads(f.read_text()):
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
