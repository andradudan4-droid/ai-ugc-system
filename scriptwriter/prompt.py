"""Build the Agent 3 prompt from brand.md + one angle.

docs/DESIGN.md §6: Phase B runs agents 0->3 manually from saved playbook prompts, and Phase B must
write the same artifact formats Phase A will read. So the prompt is the deliverable here -- the
same text drives a manual run today and an API call later, and both return scripts.json.
"""

from __future__ import annotations

import json
import pathlib
import re

from .angles import EVIDENCE_NOTE, SATURATION_NOTE, evidence_grade

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRANDS = ROOT / "data" / "brands"

SYSTEM = """You write short-form UGC ad scripts for DTC beauty and skincare brands.

You are given one brand brief and one creative angle. Write {n} distinct scripts that execute THAT
angle for THAT brand. Not variations on a theme — distinct executions, each with a different opening
move, a different objection handled, and a different reason to keep watching past second three.

Non-negotiable:

1. `hook` is what is SPOKEN in the first 1–3 seconds. It is not a title or a summary. It must work
   with the sound off at a glance and with the sound on as a sentence. Never open with the brand
   name, "introducing", or a greeting.
2. Every efficacy claim you write must also appear verbatim in `claims_used`. If you cannot source a
   claim from the brief, do not write it. Prefer sensory and experiential language over efficacy.
3. Obey the brief's "Do not say" list exactly. Those phrases appear in the brand's own marketing but
   are not substantiated for paid social. Do not rephrase around them either — no "gets rid of",
   "fixes", "clears up" as a synonym for a treatment claim.
4. `avatar_brief` must be specific enough for a casting decision: age band, presentation, setting,
   and delivery energy. "A woman in her 30s" is not enough.
5. Name a real SKU from the brief in `product`. Use the real price if the brief gives one.
6. Beats must be ordered by `t` and the last beat must land the CTA. Total `duration_s` between 15
   and 45.

Return ONLY a JSON array of script objects, no prose around it. Each object:

{schema}
"""

USER = """## Brand brief

{brand_md}

## Angle to execute

- **angle_id:** {angle_id}
- **label:** {label}
- **description:** {description}
- **saturation:** {saturation}
- **evidence grade:** {evidence}

**Competitive position:** {saturation_note}

**How much to lean on this angle's wording:** {evidence_note}
{examples_block}{scope_block}
Set `angle_id` to "{angle_id}" and `source_hook_ids` to {hook_ids} on every script you return.
Set `brand_slug` to "{brand_slug}", `provenance` to "{provenance}", and `status` to "draft".
Use script_id "{brand_slug}-{angle_id}-01", "-02", ... in order.
"""

SCHEMA_SKETCH = {
    "script_id": "<brand_slug>-<angle_id>-01",
    "brand_slug": "<slug>",
    "angle_id": "<angle_id>",
    "source_hook_ids": ["<hook_id>"],
    "product": "<real SKU name from the brief>",
    "avatar_brief": "<age band, presentation, setting, delivery energy>",
    "hook": "<spoken words, first 1-3 seconds>",
    "first_frame": "<what is on screen at t=0>",
    "beats": [{"t": 0, "vo": "<spoken>", "visual": "<on screen>"}],
    "cta": "<spoken call to action>",
    "duration_s": 30,
    "claims_used": ["<every efficacy claim spoken, verbatim>"],
    "provenance": "<passed through>",
    "status": "draft",
}


def brand_md(slug: str) -> str:
    p = BRANDS / slug / "brand.md"
    if not p.exists():
        raise SystemExit(f"no brand.md for {slug} — run Agent 0 first")
    return p.read_text()


def do_not_say(md: str) -> list[str]:
    """Pull the Do-not-say list back out of brand.md so it can be checked after generation."""
    m = re.search(r"## Do not say\n(.*?)(?=\n## |\Z)", md, re.S)
    return re.findall(r'^- "([^"]+)"', m.group(1), re.M) if m else []


def _examples_block(angle: dict) -> str:
    ex = angle.get("examples") or []
    if not ex:
        return ""
    lines = "\n".join(f"  - {e}" for e in ex[:5])
    return (
        "\n**Openings already running in this angle** (ad copy, NOT spoken hooks — read them for "
        f"what is already taken, then go elsewhere):\n{lines}\n"
    )


def _scope_block(corpus: dict) -> str:
    w = corpus.get("scope_warning")
    a = corpus.get("absence_is_measured_on")
    if not (w or a):
        return ""
    return "\n**Scope of the evidence:** " + " ".join(x for x in (w, a) if x) + "\n"


def build(slug: str, angle: dict, n: int, provenance: str, corpus: dict | None = None) -> dict:
    md = brand_md(slug)
    corpus = corpus or {}
    grade = evidence_grade(angle)
    return {
        "brand_slug": slug,
        "angle_id": angle["angle_id"],
        "provenance": provenance,
        "angle_evidence": grade,
        "angle_saturation": angle.get("saturation", "unclaimed"),
        "do_not_say": do_not_say(md),
        "system": SYSTEM.format(n=n, schema=json.dumps(SCHEMA_SKETCH, indent=2)),
        "user": USER.format(
            brand_md=md,
            angle_id=angle["angle_id"],
            label=angle["label"],
            description=angle["description"],
            saturation=angle.get("saturation", "unclaimed"),
            saturation_note=SATURATION_NOTE.get(angle.get("saturation", "unclaimed"), ""),
            evidence=grade,
            evidence_note=EVIDENCE_NOTE[grade],
            examples_block=_examples_block(angle),
            scope_block=_scope_block(corpus),
            hook_ids=json.dumps(angle["hook_ids"]),
            brand_slug=slug,
            provenance=provenance,
        ),
    }
