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
    # Restored after being folded into story_open during the v3 rule rebuild. That was an
    # unintended loss: origin/provenance is a distinct argument from narrative-open, and it is one
    # of only two angles Froya own.
    ("heritage_origin", "provenance",
     r"viking|born where winters|nordic|arctic women|scandinavian wisdom|ancient .{0,12}recipe"
     r"|norwegian|aussie outback|from the .{0,15}(outback|fjords|meadows)"),
    ("story_open", "narrative",
     r"^her name is|every teacher called|thousands of women are getting"),
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


# Ad Library keyword-search probes, run 2026-09-19 against ALL advertisers rather than our own
# sample. This is the only evidence here that can FALSIFY an unclaimed claim: a corpus of 12 brands
# can fail to contradict an angle forever without ever testing it. Four of the five probed angles
# turned out to be claimed, so corpus-absence should be treated as a hypothesis, not a finding.
EXTERNAL_PROBES = {
    "menopause_skin": {
        "verdict": "CLAIMED", "query": "menopause skin", "results": "~100",
        "evidence": [
            "Maelove — topical facial skincare, runs it in hook position: 'Perimenopause changed "
            "my skin before I even realized what was happening... When estrogen drops, collagen "
            "production slows'. Live since 22 Jul 2026. Maelove is in our own candidates.json; "
            "our 12-brand sample simply did not include it.",
            "Olay — #perimenopause #midlifewomen creator ad. Olay is in targets.csv.",
            "Michael Todd Beauty — 7 ads on 'After 40, estrogen shifts change your skin'.",
        ],
    },
    "glp1_facial_volume_loss": {
        "verdict": "CLAIMED_ADJACENT", "query": "ozempic face", "results": "~120",
        "evidence": [
            "Worked hard, but by INGESTIBLES, not topical skincare: Ownist Global (collagen shot), "
            "Lemon & Co. (collagen elixir, live since 30 Oct 2025), Heart & Soil (GLP-1 stack).",
            "No topical facial skincare advertiser found running it. Still open for a topical "
            "brand -- but the audience has already been taught the frame by supplement ads, so it "
            "is not virgin territory.",
        ],
    },
    "pregnancy_safe": {
        "verdict": "CLAIMED", "query": "pregnancy safe skincare", "results": "~6",
        "evidence": [
            "Primally Pure Skincare — topical, creator ad, pregnancy-safe switch as the hook.",
            "Secret Saviours — topical pregnancy skincare system.",
            "Tiny field (6 ads total vs ~33,000 mentioning menopause), so claimed but barely "
            "contested -- arguably the most attractive of the demoted angles.",
        ],
    },
    "skin_as_signal": {
        "verdict": "CLAIMED_ADJACENT", "query": "gut health skin", "results": "~75",
        "evidence": [
            "Clarity Complex — 'Stubborn Jawline Breakouts? These need an inside out approach', "
            "live since 11 May 2026. Ingestible, not topical.",
            "Most results are pet supplements. No topical skincare advertiser found.",
        ],
    },
    "male_facing": {
        "verdict": "CLAIMED", "query": "skincare for men", "results": "~44",
        "position": "hook",
        "evidence": [
            "Brickell Men's Products opens on it: 'Most men don't want a skincare routine.' Live "
            "since 9 Jul 2026, 3 ads on the creative.",
            "LAB SERIES (Jordan Clarkson partnership), Hommeface: Skincare for Men.",
        ],
    },
    "dermatologist_as_ally": {
        "verdict": "UNCLAIMED_POSITION", "query": "my dermatologist", "results": "~2,300",
        "position": "body",
        "evidence": [
            "Term is common in the category, but no hook-position use was found -- the pattern "
            "already seen with DRMTLGY's 'Dermatologist Recommended' trust bullet.",
            "CONFIDENCE LOW: ~2,300 results and only the first page was read. The claim is "
            "'no opener found in what was sampled', not 'no opener exists'.",
        ],
    },
    "reactive_sensitive_identity": {
        "verdict": "UNCLAIMED_POSITION", "query": "reactive skin", "results": "~510",
        "position": "body",
        "evidence": [
            "Present in the category (Michael Todd Beauty, Circadia) but not as the identity the "
            "ad opens on.",
            "CONFIDENCE LOW: first page of ~510 only.",
        ],
    },
    "prevention_early": {
        "verdict": "UNCLAIMED_POSITION", "query": "preventative skincare", "results": "~16",
        "position": "body",
        "evidence": [
            "GoPure Skin Care uses the phrase mid-copy, opening instead on 'I used to think "
            "skincare stopped at my chin'. Term used as a qualifier, never as the opening.",
            "Tiny field -- 16 ads in the whole category.",
            "NOTE: a first probe, 'prevent wrinkles in your 20s', returned zero. That was an "
            "invented phrase and its zero was discarded rather than recorded -- it would have "
            "tested our vocabulary, not the category.",
        ],
    },
    "water_quality": {
        "verdict": "HOLDS", "query": "hard water", "results": "~3,600",
        "evidence": [
            "All results are cleaning and appliance products -- dishwasher powder, washing machine "
            "tablets, hard-water spot remover. No skincare advertiser found.",
            "Note eskiin works this angle hard, but it is a filtered showerhead and was excluded "
            "from this corpus as beauty_device.",
        ],
    },
}

UNPROBED_NOTE = ("Not yet probed externally. Corpus-absence only, which the probed angles just "
                 "showed is weak evidence -- 4 of 5 tested turned out to be claimed. Treat as an "
                 "untested hypothesis, not a finding.")


def classify(text: str) -> tuple[str, str]:
    t = text.lower().strip()
    for angle, htype, pat in RULES:
        if re.search(pat, t, re.I):
            return angle, htype
    return "unclassified", "other"


CORPUS_CLASS = "topical_skincare"

# Monotonic. Bump on any change to the corpus or the rules. Consumers pin what they built against
# and refuse to assemble when it moves -- Writer had an angle vanish under them between 2 and 3.
CORPUS_VERSION = 4


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
            # Strategy's concentration gate: a category claim needs >=3 brands and no single brand
            # holding >30% of the evidence. Emitting the distribution is what makes that testable.
            "brand_distribution": dict(collections.Counter(r["brand"] for r in rows)),
            "max_brand_share": round(
                max(collections.Counter(r["brand"] for r in rows).values()) / len(rows), 2),
            "examples": [r["hook_text"][:110] for r in rows[:3]],
        })
    angles.sort(key=lambda x: (-x["brand_count"], -x["ad_count"]))

    # saturated = run by 2+ brands AND with a long-lived ad behind it
    for a in angles:
        a["saturation"] = ("saturated" if a["brand_count"] >= 2 and a["max_days_running"] >= 90
                           else "contested" if a["brand_count"] >= 2
                           else "single_brand")

    unclaimed, position, claimed = [], [], []
    for key, desc, probe in CANDIDATES:
        hits = [h["hook_text"][:90] for h in hooks if re.search(probe, h["hook_text"], re.I)]
        entry = {"angle": key, "description": desc, "probe": probe, "corpus_hits": len(hits)}
        ext = EXTERNAL_PROBES.get(key)
        entry["external_probe"] = ext or {"verdict": "UNPROBED", "note": UNPROBED_NOTE}
        if hits:
            entry["example_hits"] = hits[:3]
        verdict = ext["verdict"] if ext else "UNPROBED"
        if hits or verdict in {"CLAIMED", "CLAIMED_ADJACENT"}:
            claimed.append(entry)
        elif verdict == "UNCLAIMED_POSITION":
            position.append(entry)
        else:
            unclaimed.append(entry)

    fingerprint = hashlib.sha256(
        "|".join(sorted(h["ad_id"] for h in hooks)).encode()
    ).hexdigest()[:16]


    # The corpus fingerprint tracks the HOOKS. It deliberately does not move when only a verdict
    # changes -- but a verdict change is precisely what invalidates a script written against an
    # unclaimed angle, so the claims get their own fingerprint to fail on.
    claims_fingerprint = hashlib.sha256(
        "|".join(f"{c['angle']}={c.get('external_probe', {}).get('verdict', '?')}"
                 for c in sorted(unclaimed + position + claimed,
                                 key=lambda x: x["angle"])).encode()
    ).hexdigest()[:16]

    return {
        "schema_version": 3,
        "corpus_version": CORPUS_VERSION,
        "claims_fingerprint": claims_fingerprint,
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
        # The sharpest category in the file. These angles EXIST in the market but nobody opens on
        # them, so the claim is positional and survives a brand pointing at its own body copy --
        # unlike a bare absence claim, which that rebuttal kills.
        "unclaimed_position_angles": position,
        "claimed_angles": claimed,
    }


def write(payload: dict, path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path
