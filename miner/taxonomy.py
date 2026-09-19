"""Agent 2 (Taxonomist): hooks.jsonl -> angles.json.

Two outputs, and the second is the one that gets sold:

  saturated   angles many brands are running, on ads that have survived 30+ days. Evidence of
              what works AND of where a new entrant will be shouting into a crowd.
  unclaimed   angles that live in the category's problem space but that nobody in the corpus is
              running. This is the commercial output (docs/DESIGN.md §4).

An "unclaimed" claim is the easiest thing in this system to get wrong and the most expensive,
because it is what a brand pays for. So it is not asserted here -- each candidate carries probe
terms and is *verified* against the corpus at build time. If a probe hits, the angle is demoted to
`claimed` automatically and reported as such. The absence is computed, never declared.
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import pathlib
import re

# ---- hook taxonomy -------------------------------------------------------------------
# (angle, hook_type, pattern). First match wins, so order is specificity order.
RULES: list[tuple[str, str, str]] = [
    # Displacing a clinic procedure. The category's single biggest argument -- it shows up as
    # attack (Botox is a lie), as substitution (needle-free, skip the needles) and as price math.
    ("injectable_displacement", "enemy_reframe",
     r"\bbotox\b|filler migration|never touched botox|\$500 every 3 months|gastando \$500|microneedl"
     r"|needle-?free|without needles|skip the needles|no needles|peptide threads|silk peptide"
     r"|expensive laser|expensive facial|botox alternative|lift in a bottle"),
    ("ingredient_villain", "enemy_reframe",
     r"retinol is ruining|peptide lie|hyaluronic acid\?|drugstore anti-aging routines"),
    # Leaving an adjacent product category behind -- makeup, concealer, foundation.
    ("category_switch", "enemy_reframe",
     r"gave up eye concealer|ditch the concealer|stopped wearing makeup|give foundation the flick"
     r"|stage makeup gets all the credit|not makeup"),
    ("failed_solutions", "empathy_callout",
     r"you've tried the|i thought i was taking care|it started with a few fine lines"
     r"|bathroom counters look like a chemistry lab|dozens of products|zero results"
     r"|exhausted from trying everything|works when nothing else has"),
    ("skeptic_convert", "objection_open",
     r"another firming cream|yeah, sure|not gonna lie|too good to be true|i said that too"),
    ("symptom_callout", "problem_open",
     r"having skin issues|struggling with|tired of (sagging|expensive|dull)|got tired morning eyes"
     r"|dark circles|puffiness|if you're 40\+|date night\?|sagging under eyes"),
    ("age_callout", "audience_open",
     r"over 50 skincare|i'm 38|if you're 40|women over|in your 40s|fifty ?four"),
    ("mechanism_explainer", "curiosity_gap",
     r"nad\+|autophagy|nobel prize|harvard dermatology|isn't just gravity|won't believe why"
     r"|isn't luck|two actives, one mission|stops producing"),
    ("third_party_verdict", "authority_borrow",
     r"beauty editor|makeup artist|influencer saw|skincareaddiction|facts are facts|these celebs"),
    ("story_open", "narrative",
     r"^her name is|viking|born where winters|every teacher called|thousands of women are getting"),
    ("customer_testimonial", "social_proof",
     r"^[\"\u201c]|-becca|-april|julissa|literally transformed|i love this liquid collagen"
     r"|realmente me gusta|ya no como snacks"),
    ("ingredient_discovery", "curiosity_gap",
     r"anti-aging (ingredient|product) you|meet earth tones|korean advanced|arnica, sea buckthorn"
     r"|arctic plants|retinol, made gentle|pdrn \+ caviar|beef tallow|melanin-rich"),
    ("routine_simplification", "pov_format",
     r"^pov:|fits in your pocket|one balm|1 system replaces|2 steps for|dream team|bundle"
     r"|simplify your routine|shop authentic korean|glow up bundle|complete care|perfect pair"),
    ("result_first", "outcome_claim",
     r"this is how i got glowing skin|brighten your skin for a healthy glow|so hydrated this summer"
     r"|you need this|skin to glow|warm-weather skin staple|upgrade your basic shower"
     r"|visibly smooth fine lines|at-home facial|glass skin overnight|glow on the go"
     r"|your new go-to|experience a brighter|experience firmer"),
    # Opening with the SKU name. Not a hook at all -- named so the corpus can show how much of the
    # category never writes one, which is itself the opportunity.
    ("product_spec_open", "no_hook",
     r"^(the )?(good molecules|navaro|biodance|jiyu|saltair|drmtlgy)\b|are a targeted treatment"
     r"|^[a-z ]*(eye gel|ampoule|serum|patches|cream)\b.{0,40}$|powered by melting"),
    ("launch_scent", "newness",
     r"just launched|just dropped|meet your new|sells out fast|is here|new saltair|coral coast"),
    ("retail_availability", "convenience", r"target run|available at target|stocking up"),
]

# ---- candidate unclaimed territory ----------------------------------------------------
# Each is real buying territory in skincare. `probe` is what the corpus is searched for to decide
# whether it is genuinely absent. Written to be generous -- a probe that is too narrow would
# manufacture a false "unclaimed".
CANDIDATES = [
    ("glp1_facial_volume_loss",
     "GLP-1 / weight-loss facial volume loss ('Ozempic face') — rapid loss deflates the midface and is the single loudest skin conversation of the moment.",
     r"ozempic|glp-?1|weight ?loss|semaglutide|gaunt|volume loss|hollow"),
    ("menopause_skin",
     "Perimenopause / menopause skin — estrogen decline changes barrier, collagen and oil within months. The corpus sells to 40+ women without ever naming the transition they are in.",
     r"menopaus|perimenopaus|estrogen|hormonal shift|hot flash|hrt"),
    ("pregnancy_safe",
     "Pregnancy- and nursing-safe actives — a hard constraint that forces a routine rebuild and makes switching brand-agnostic.",
     r"pregnan|nursing|breastfeed|trying to conceive|postpartum|baby-safe"),
    ("reactive_sensitive_identity",
     "Reactive / sensitive skin as identity, not spec — 'if your face reacts to everything'. Barrier appears in the corpus only as mechanism inside body copy, never as who the viewer is.",
     r"reacts to everything|sensitive skin lead|rosacea|eczema|allergic|stings|flare"),
    ("dermatologist_as_ally",
     "Dermatologist as ally. Every derm reference in the corpus is adversarial — dismissive, hiding something, overprescribing. Nobody runs calm, genuine clinical endorsement, which is wide open precisely because everyone vacated it.",
     r"dermatologist recommend|my dermatologist said|derm-approved|board-certified"),
    ("male_facing",
     "Men's skin. Zero male-addressed hooks in the corpus; the entire sample speaks to women.",
     r"\bmen\b|\bhis\b|boyfriend|husband|guys|dad\b|beard"),
    ("prevention_early",
     "Prevention for under-30s — selling before damage, to an audience the corpus only addresses after the fact.",
     r"in your 20s|before it starts|prevent(ion|ative) routine|early twenties|gen z"),
    ("skin_as_signal",
     "Skin as diagnostic signal of sleep, stress, gut or hydration — reframes skincare as reading the body rather than coating it.",
     r"your gut|sleep is|stress is showing|cortisol|what your skin is telling"),
    ("water_quality",
     "Water quality — hard water and chlorine as the upstream cause. Adjacent categories run this hard; no skincare brand in the corpus touches it.",
     r"hard water|tap water|chlorine|shower filter|limescale"),
]


def classify(text: str) -> tuple[str, str]:
    t = text.lower().strip()
    for angle, htype, pat in RULES:
        if re.search(pat, t, re.I):
            return angle, htype
    return "unclassified", "other"


CORPUS_CLASS = "topical_skincare"


def build(all_hooks: list[dict]) -> dict:
    # docs/DESIGN.md §4 keys the corpus by category, and that is the whole reason it compounds.
    # A body-care or ingestible ad answers a different buyer, so it is excluded rather than diluted
    # in -- silently or otherwise. The excluded counts stay in the payload so the call is auditable.
    hooks = [h for h in all_hooks if h.get("product_class", CORPUS_CLASS) == CORPUS_CLASS]
    excluded = [h for h in all_hooks if h.get("product_class", CORPUS_CLASS) != CORPUS_CLASS]

    for h in hooks:
        h["angle"], h["hook_type"] = classify(h["hook_text"])

    corpus = " \n ".join(h["hook_text"].lower() for h in hooks)

    by_angle = collections.defaultdict(list)
    for h in hooks:
        if h["angle"] != "unclassified":       # coverage metric, not an angle
            by_angle[h["angle"]].append(h)

    angles = []
    for a, rows in by_angle.items():
        brands = sorted({r["brand"] for r in rows})
        angles.append({
            "angle": a,
            "hook_type": rows[0]["hook_type"],
            "brands": brands,
            "brand_count": len(brands),
            "ad_count": len(rows),
            "median_days_running": sorted(r["days_running"] for r in rows)[len(rows) // 2],
            # consumed by Writer's evidence_grade(); absent -> it degrades to the cautious branch
            "hook_sources": dict(collections.Counter(r.get("hook_source", "unknown") for r in rows)),
            "max_days_running": max(r["days_running"] for r in rows),
            # DESIGN.md §2 wants every asset traceable to the angle AND the hook behind it.
            # Carrying the ad ids through is what lets a consumer complete that chain.
            "hook_ids": sorted(r["ad_id"] for r in rows),
            "examples": [r["hook_text"][:110] for r in rows[:3]],
        })
    angles.sort(key=lambda x: (-x["brand_count"], -x["ad_count"]))

    # saturated = run by 2+ brands AND with a long-lived ad behind it
    for a in angles:
        a["saturation"] = ("saturated" if a["brand_count"] >= 2 and a["max_days_running"] >= 90
                           else "contested" if a["brand_count"] >= 2
                           else "single_brand")

    unclaimed, demoted = [], []
    for key, desc, probe in CANDIDATES:
        hits = [h["hook_text"][:90] for h in hooks if re.search(probe, h["hook_text"], re.I)]
        entry = {"angle": key, "description": desc, "probe": probe, "corpus_hits": len(hits)}
        if hits:
            entry["example_hits"] = hits[:3]
            demoted.append(entry)
        else:
            unclaimed.append(entry)

    fingerprint = hashlib.sha256(
        "|".join(sorted(h["ad_id"] for h in hooks)).encode()
    ).hexdigest()[:16]

    return {
        "schema_version": 2,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        # Changes iff the underlying hook set changes. A consumer that stamped one value and sees
        # another has been rebuilt out from under it and should fail rather than reconcile.
        "corpus_fingerprint": fingerprint,
        "corpus": {
            "product_class": CORPUS_CLASS,
            "hook_sources": dict(collections.Counter(h.get("hook_source", "unknown") for h in hooks)),
            "excluded_off_category": {
                "hooks": len(excluded),
                "by_class": dict(collections.Counter(h["product_class"] for h in excluded)),
                "note": ("Mined but kept out of the skincare corpus. SpoiledChild advertises "
                         "ingestible collagen, appetite suppression and hair thinning; Saltair "
                         "advertises body wash, body oil, deodorant and fragrance. Both are tagged "
                         "skincare at brand level in targets.csv -- the ad copy says otherwise."),
            },
            "hooks": len(hooks),
            "classified": sum(1 for h in hooks if h["angle"] != "unclassified"),
            "unclassified": sum(1 for h in hooks if h["angle"] == "unclassified"),
            "brands": sorted({h["brand"] for h in hooks}),
            "min_days_running": min(h["days_running"] for h in hooks),
            "scope_warning": (
                "PILOT CORPUS — 5 fatigued brands of 81 in scope. 'unclaimed' means absent from "
                "THIS sample, not proven absent from the category. Verify against the full 81 "
                "before putting an unclaimed angle in front of a client."
            ),
            "absence_is_measured_on": (
                "Hook position only — the ad's opening line, which is what was captured in full. "
                "Body copy was stored truncated, so NO claim is made about whether an angle "
                "appears deeper in an ad, and the probes must not be read as evidence about it. "
                "Observed directly while collecting: DRMTLGY runs '🩺 Dermatologist Recommended' "
                "as a trust bullet. So dermatologist_as_ally exists in the category as "
                "reassurance and is still unclaimed as an opening argument — which is the unit "
                "being sold, and a sharper finding than simple absence."
            ),
        },
        "saturated_angles": [a for a in angles if a["saturation"] == "saturated"],
        "contested_angles": [a for a in angles if a["saturation"] == "contested"],
        "single_brand_angles": [a for a in angles if a["saturation"] == "single_brand"],
        "unclaimed_angles": unclaimed,
        "demoted_candidates": demoted,
    }


def write(payload: dict, path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path
