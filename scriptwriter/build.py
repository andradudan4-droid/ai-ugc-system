"""Emit Agent 3 prompts and assemble returned scripts into scripts.json."""

from __future__ import annotations

import json
import pathlib
import re

from .angles import FixtureData, evidence_grade, guard_publish, load
from .prompt import build as build_prompt
from .schema import validate

# CLIENT-READINESS IS GATED PER CLAIM, NOT PER CORPUS.
#
# Ask what failure the gate prevents. The one actually hit: customer_testimonial inverted because
# ONE brand's ingestible ads dominated a 4-brand sample. That is a CONCENTRATION failure, not a
# volume failure -- and a hook count cannot see it, which is why an earlier 150-hook bar punished
# the off-category cleaning that fixed it. Brand count alone is also too crude: 12 brands where one
# contributes 100 hooks and eleven contribute three is just as invertible.
#
# So each script is gated on the specific claim it rests on:
#   category_pattern  ("the category runs X")     >=3 brands AND no brand over 30% of the evidence
#   category_absence  ("the category doesn't")    corpus floor only; absence is measured corpus-wide
#   single_brand      (one other brand does X)    NOT client-ready as a category finding -- label it
#   brand_own         (this client's own ads)     no category evidence needed; it is an observation
#                                                 about the client, not about the market
#   category_pattern  ("the category runs X")     LEAVE-ONE-OUT: drop the largest contributing
#                                                  brand entirely; >=3 brands and >=5 ads must
#                                                  remain. Asks the question that matters -- is this
#                                                  a pattern, or one advertiser being loud -- and is
#                                                  scale-free, so it needs no separate sample floor.
#
# The previous rule (>=3 brands AND no brand over 30%) was unsatisfiable: at exactly 3 brands the
# smallest possible largest share is 33.3%, so a 3-brand angle could never pass whatever the data
# said. It also scored MORE evidence worse -- a 3-ad even split cleared a bar a 38-ad angle failed.
CORPUS_MIN_BRANDS = 8       # floor for any category-level claim at all
LOO_MIN_BRANDS = 3          # brands remaining after dropping the largest contributor
LOO_MIN_ADS = 5             # ads remaining after dropping the largest contributor

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


def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _hooks_by_ad_id() -> dict[str, dict]:
    f = SHARED / "hooks.jsonl"
    if not f.exists():
        return {}
    out = {}
    for line in f.read_text().splitlines():
        if line.strip():
            h = json.loads(line)
            out[str(h.get("ad_id"))] = h
    return out


def brand_mix(angle: dict) -> dict[str, int]:
    """Ads per brand behind one angle.

    Resolved through the angle's own `hook_ids` against hooks.jsonl's `ad_id`. Agent 2 does not
    write its classification back onto the hook rows (`angle` is null on all of them), so joining
    on that field silently yields nothing -- which, with the fail-closed rule, blocked every
    category claim. Empty here still means "could not check", and still fails closed.
    """
    ids = angle.get("hook_ids") or []
    if not ids:
        return {}
    by_ad = _hooks_by_ad_id()
    mix: dict[str, int] = {}
    for i in ids:
        h = by_ad.get(str(i))
        if h:
            b = h.get("brand", "?")
            mix[b] = mix.get(b, 0) + 1
    return mix


def claim_gate(angle: dict, brand_slug: str, corpus: dict, is_fixture: bool) -> tuple[bool, str, str]:
    """Return (client_ready, claim_type, reason) for one script's underlying claim."""
    if is_fixture:
        return False, "fixture", "Generated from a hand-written FIXTURE. Not real evidence."

    corpus_brands = len(corpus.get("brands", []))
    brands = angle.get("brands", [])
    owns_it = len(brands) == 1 and _norm(brands[0]) in _norm(brand_slug)

    if owns_it:
        return True, "brand_own", (
            f"Observation about the client's own ads ({angle.get('ad_count', 0)} ads). Needs no "
            "category evidence — it is not a claim about the market."
        )

    if angle.get("saturation") == "unclaimed":
        if corpus_brands < CORPUS_MIN_BRANDS:
            return False, "category_absence", (
                f"Absence claim against only {corpus_brands} brands, below the "
                f"{CORPUS_MIN_BRANDS}-brand floor."
            )
        return True, "category_absence", (
            f"Absence measured across the whole corpus: {corpus.get('hooks', 0)} hooks from "
            f"{corpus_brands} brands, zero hits."
        )

    n_brands = angle.get("brand_count") or len(brands)
    if n_brands < LOO_MIN_BRANDS:
        return False, "single_brand", (
            f"Only {n_brands} brand(s) behind this angle ({', '.join(brands) or 'unknown'}). "
            "Usable as an observation, NOT sellable as a category finding."
        )

    mix = brand_mix(angle)
    total = sum(mix.values())
    if total:
        top, top_n = max(mix.items(), key=lambda kv: kv[1])
        rest = {b: n for b, n in mix.items() if b != top}
        rest_ads, rest_brands = sum(rest.values()), len(rest)
        if rest_brands < LOO_MIN_BRANDS or rest_ads < LOO_MIN_ADS:
            return False, "category_pattern", (
                f"Leave-one-out failure: drop {top} ({top_n}/{total} ads) and only {rest_ads} ads "
                f"across {rest_brands} brands remain (need {LOO_MIN_ADS}/{LOO_MIN_BRANDS}). This is "
                "one advertiser being loud, not a category pattern."
            )
        return True, "category_pattern", (
            f"Holds without its largest contributor: drop {top} ({top_n}/{total} ads) and "
            f"{rest_ads} ads across {rest_brands} brands remain. Largest brand is "
            f"{top_n / total:.0%} of the evidence."
        )
    # No per-brand distribution available means the concentration check could not run. That is an
    # unknown, and an unknown must fail closed -- not pass because the evidence was missing.
    return False, "category_pattern", (
        f"Concentration check could not run: no resolvable hook_ids for '{angle['angle_id']}' "
        "against hooks.jsonl. A category claim is not client-ready without it."
    )


def _drift(corpus: dict) -> dict | None:
    """Did the evidence move since the last published build? Reports which fingerprint changed."""
    prev_f = OUT / "scripts.json"
    if not prev_f.exists():
        return None
    try:
        prev = json.loads(prev_f.read_text())
    except json.JSONDecodeError:
        return None
    moved = {}
    for k in ("corpus_fingerprint", "claims_fingerprint"):
        was, now = prev.get(k), corpus.get(k)
        if was and now and was != now:
            moved[k] = {"was": was, "now": now}
    return moved or None


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
    ids = angle.get("hook_ids") or []
    trace = f"{len(ids)} hook ids" if ids else "NO hook ids in angles.json — angle-level only"
    return (
        f"angle={aid} ({sat}, {n} ads across {brands}); traceable to {trace}. Evidence grade {grade}."
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
            ok, claim_type, why = claim_gate(a, slug, corpus, is_fixture)
            s["claim_type"] = claim_type
            s["claim_evidence"] = why
            s["corpus_fingerprint"] = corpus.get("corpus_fingerprint")
            s["claims_fingerprint"] = corpus.get("claims_fingerprint")
            s["client_ready"] = ok
            if not ok:
                s["hold_reason"] = why
            elif claim_type == "category_absence":
                # Absence can only be disproved by more data, and six of the nine unclaimed angles
                # are about WHO is addressed -- which caption copy may not be able to see at all.
                # So an absence claim stays held until the transcription pass can reject it.
                s["client_ready"] = False
                s["hold_reason"] = (
                    "Absence claim, evidenced on caption openings only. Six of the nine unclaimed "
                    "angles concern who is being addressed, which caption text may not capture — "
                    "so these may have survived a test unable to reject them. Held until Agent 2's "
                    "transcription pass lands."
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
        "corpus_fingerprint": corpus.get("corpus_fingerprint"),
        "claims_fingerprint": corpus.get("claims_fingerprint"),
        "schema_version": corpus.get("schema_version"),
        "evidence_moved_since_last_build": _drift(corpus),
        "client_ready": all(x["client_ready"] for x in scripts) if scripts else False,
        "client_ready_reason": "Gated per claim — see claim_type and claim_evidence on each script.",
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
