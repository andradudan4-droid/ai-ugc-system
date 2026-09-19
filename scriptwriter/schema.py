"""The scripts.json contract (docs/DESIGN.md §3, Agent 3 -> Agent 4/5).

DESIGN.md names the artifact but does not specify its fields, so this module defines them. Shape is
driven by what the two consumers need:

- Agent 4 (render queue) needs, per script, one renderable unit: an avatar brief, ordered beats with
  voiceover and on-screen direction, and a duration.
- Agent 5 (QA) checks audio sync, avatar/demographic match to brief, product visibility, first-frame
  scroll-stop and visual artifacts -- so `avatar_brief`, `product`, and a distinct `hook` with its
  own first-frame direction all have to be addressable on their own, not buried in prose.

DESIGN.md §2 requires attribution: every asset traces back to the angle and hook that produced it.
`angle_id` and `source_hook_ids` carry that and are mandatory.
"""

from __future__ import annotations

REQUIRED = [
    "script_id",        # stable id: <brand_slug>-<angle_id>-<nn>
    "brand_slug",       # matches data/brands/<slug>/
    "angle_id",         # attribution -> angles.json
    "source_hook_ids",  # attribution -> hooks.jsonl; EMPTY when Agent 2 carries no hook ids
    "attribution_basis",  # plain-English record of what this script can actually be traced to
    "angle_saturation",   # saturated | contested | single_brand | unclaimed
    "product",          # the SKU this script sells, from brand.md
    "avatar_brief",     # who delivers it: age band, presentation, setting
    "hook",             # spoken first 1-3s -- Agent 5's scroll-stop check
    "first_frame",      # what is on screen at t=0
    "beats",            # list[{t, vo, visual}] in order, t in seconds
    "cta",
    "duration_s",
    "claims_used",      # list[str] -- every efficacy claim spoken
    "angle_evidence",   # transcribed | copy_derived | mixed | unknown -- see angles.py
    "provenance",       # where the angle came from; FIXTURE output is marked here
    "claim_type",       # brand_own | category_pattern | category_absence | single_brand | fixture
    "claim_evidence",   # what the claim rests on, stated in full
    "corpus_fingerprint",  # which corpus version this was built against
    "client_ready",     # gated per claim -- see build.claim_gate()
    "status",           # draft | approved | rendered
]

ALLOWED_STATUS = {"draft", "approved", "rendered"}
ALLOWED_EVIDENCE = {"transcribed", "copy_derived", "mixed", "unknown"}
ALLOWED_SATURATION = {"saturated", "contested", "single_brand", "unclaimed"}


def validate(script: dict) -> list[str]:
    """Return a list of contract violations; empty means valid."""
    errs = []
    for f in REQUIRED:
        if f not in script:
            errs.append(f"missing field: {f}")

    if script.get("status") not in ALLOWED_STATUS:
        errs.append(f"status must be one of {sorted(ALLOWED_STATUS)}")
    if script.get("angle_evidence") not in ALLOWED_EVIDENCE:
        errs.append(f"angle_evidence must be one of {sorted(ALLOWED_EVIDENCE)}")

    if not script.get("angle_id"):
        errs.append("angle_id is empty -- breaks attribution (DESIGN.md §2)")
    # DESIGN.md §2 wants every asset traced to the angle AND hook that produced it. Agent 2 does
    # not carry hook ids through, so hook-level attribution is often impossible. Record that gap in
    # attribution_basis rather than fabricating ids to satisfy the field.
    if not isinstance(script.get("source_hook_ids"), list):
        errs.append("source_hook_ids must be a list (may be empty)")
    basis = (script.get("attribution_basis") or "").strip()
    if len(basis) < 20:
        errs.append("attribution_basis must say what this traces back to, and what it does not")
    if not isinstance(script.get("client_ready"), bool):
        errs.append("client_ready must be a bool")
    if script.get("client_ready") is False and not (script.get("hold_reason") or "").strip():
        errs.append("client_ready False requires a hold_reason")
    if script.get("angle_saturation") not in ALLOWED_SATURATION:
        errs.append(f"angle_saturation must be one of {sorted(ALLOWED_SATURATION)}")

    beats = script.get("beats")
    if not isinstance(beats, list) or not beats:
        errs.append("beats must be a non-empty list")
    else:
        for i, b in enumerate(beats):
            for k in ("t", "vo", "visual"):
                if k not in b:
                    errs.append(f"beat[{i}] missing {k}")
        ts = [b.get("t") for b in beats if isinstance(b.get("t"), (int, float))]
        if ts != sorted(ts):
            errs.append("beats must be ordered by t")

    d = script.get("duration_s")
    if not isinstance(d, (int, float)) or not (8 <= d <= 60):
        errs.append("duration_s must be a number between 8 and 60")

    if not isinstance(script.get("claims_used"), list):
        errs.append("claims_used must be a list (may be empty)")

    return errs
