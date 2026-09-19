# Agent 3 — Scriptwriter

Input: `brand.md` (Agent 0) + `angles.json` (Agent 2, owned by Miner). Output: `scripts.json`.
Cadence: per batch (`docs/DESIGN.md` §3).

## Run it

```bash
python3 run_scriptwriter.py --emit <brand_slug> [--angles A01,A08] [--n 3]
python3 run_scriptwriter.py --assemble
```

Per `docs/DESIGN.md` §6, Phase B runs this manually from saved prompts and Phase A swaps the manual
step for an API call against the *same* prompts. So `--emit` writes one prompt per angle to
`data/scripts/prompts/`; you run each, save the returned JSON array to
`data/scripts/returns/<slug>--<angle_id>.json`; `--assemble` validates and builds `scripts.json`.
No spend either way — this repo makes no model calls.

## Status: live on real angles

`angles.json` landed. The fixture is retired to a regression path — it still works and still cannot
publish, but the default source is now `shared/data/angles.json`.

Agent 2 emits angles in four saturation buckets rather than a flat list, so `angles._normalise()`
flattens them and records `saturation` per angle. That drives a second prompt instruction alongside
evidence grade: a `saturated` angle is where every long-running ad already is (one creative in
`customer_testimonial` has been alive 614 days), so writing there needs a real wedge; an `unclaimed`
angle has no examples to imitate because none exist.

**The loader refuses to run rather than return nothing.** Agent 2's real shape has no top-level
`angles` key, so a fixture-shaped loader parses it to an empty list and silently produces zero
prompts. `load()` now raises with the file's actual top-level keys instead.

## Client-readiness is a corpus gate, not a judgement

A thin corpus does not make a script wrong — it makes it unproven. `build.client_readiness()` checks
the angle corpus mechanically: under `CLIENT_READY_MIN_HOOKS` (150) or `CLIENT_READY_MIN_BRANDS` (8)
and the whole file is marked `client_ready: false`, with the reason written into `scripts.json` and a
`hold_reason` on every script. Validation rejects `client_ready: false` without a reason.

Unclaimed angles carry a second, independent hold: absence is only as strong as the corpus it was
measured against, so an unclaimed angle stays held even once the corpus clears the bar, until it is
re-confirmed against the wider sample.

The reason this is mechanical rather than a per-batch call: contamination in a 4-brand pilot already
inverted one result. `customer_testimonial` read as the most saturated angle in the category off 25
ads — 24 of them ingestible or body-care. In facial skincare it runs on **one** ad. Agent 3 steered
away from one of the emptiest positions available to the brand it was writing for, on evidence that
looked solid. A gate that only fires when someone remembers to think about it would not have fired.

## A stale angle is rejected, never defaulted

Agent 2 re-derives on new corpora and angles appear and vanish between versions — `heritage_origin`
existed in v2 (Frøya, 4 ads) and is absent from v3. Three scripts had been written against it.

The first version of this code defaulted a missing angle to `angle_saturation: "unclaimed"`. That is
not a neutral fallback: `unclaimed` is a positive claim of *verified absence* and the most sellable
label in the taxonomy, so a lookup miss silently became a stronger claim than the truth. Three stale
scripts briefly sat in the published artifact labelled as the category's best open position.

A script whose `angle_id` is not in the current `angles.json` is now **rejected**, with the angle
named in the error. Its evidentiary basis is gone and it cannot be re-validated, so it does not
belong in `scripts`. Defaults in this pipeline must fail toward the weaker claim, never the stronger
one.

## Attribution is incomplete, and says so

`docs/DESIGN.md` §2 requires every asset to trace back to the angle **and the hook** that produced
it. Agent 2 does not carry hook ids through from `hooks.jsonl`, so hook-level attribution is not
possible — and for an `unclaimed` angle there is no hook to trace to by definition, since the angle
is established by absence.

Rather than fabricate ids to satisfy a required field, every script carries `attribution_basis`
stating what it does and does not trace to:

> angle=heritage_origin (single_brand, 4 ads across Froya Organics). Agent 2 does not carry hook ids
> through from hooks.jsonl, so DESIGN.md §2 hook-level attribution is INCOMPLETE — traceable to the
> angle, not to individual ads. Evidence grade copy_derived.

Validation requires that string to be substantive, so the gap cannot be silently skipped.

## The fixture (retired)

`angles.json` does not exist yet — Agent 2 is blocked upstream on the `DESIGN.md` §10 ad-intel
decision. Agent 3 is complete and tested against `data/fixtures/angles.fixture.json`, a hand-written
set of 12 category-plausible angle labels.

**Fixture data cannot escape.** The fixture carries `_fixture: true`; every script generated from it
is stamped `FIXTURE — NOT client-safe` in `provenance`; `scripts.json` records `is_fixture` and
`publish_refused` in the file itself; and publishing to `shared/data/` is refused outright. When
Miner's real `angles.json` lands in `shared/data/`, `angles.source_path()` prefers it automatically
and the guard stops firing — no code change.

The fixture exists to get the wiring and the prompt right. Its angle labels are plausible, not
evidence — real angles come from clustering real mined hooks, and inventing them would put
fabricated "unclaimed angles" into a client deliverable.

## Angle evidence grade

Miner's `hooks.jsonl` records `hook_source` per row: a verbatim **transcribed** opening, or the
opening of the ad's **primary text**. Those are not the same artifact. The eskiin ad is the clean
illustration — its body opens *"the only high-performance filtered showerhead with 2.5x pressure and
a 15-stage filtration system"*. That is a claim block. A hook is *"I stopped washing my hair in tap
water."* An angle clustered from copy openings therefore describes a **claim space**, not a hook
space, and must not be echoed as though its wording were a proven opening line.

`angles.evidence_grade()` reduces an angle's `hook_sources` to `transcribed` / `copy_derived` /
`mixed` / `unknown` and that grade **changes the generation prompt**:

| grade | instruction to the writer |
|---|---|
| `transcribed` | the angle's shape is evidence — follow it closely |
| `copy_derived` | use it for *what* it argues, never *how* it is phrased; write the hook fresh, no claim-block cadence |
| `mixed` | transcribed share guides phrasing, the rest is argument only |
| `unknown` | degrade to the cautious branch |

`hook_sources` is accepted as either a count map or a plain list, so it survives whichever shape
Agent 2 emits. `angle_evidence` is required on every script and is stamped from the angles file at
assembly — never read from the model's own output, because a generator does not get to assert its
own provenance. If transcription later backfills a copy-derived corpus, the regrade is automatic and
scripts already produced keep the grade they were written under.

## Two guards

1. **Contract validation** (`schema.py`) — rejects a script missing attribution (`angle_id`,
   `source_hook_ids`, required by `DESIGN.md` §2), with unordered beats, or a `duration_s` outside
   8–60s.
2. **Do-not-say post-check** (`build.py`) — Agent 0 extracts each brand's unsubstantiated claim
   language into `brand.md`; the prompt passes it to the model, and then `assemble()` re-checks the
   returned script's spoken lines against it. The model is told, and then verified. Violations go to
   `rejected` with the offending phrases named, and never reach `scripts`.

Both are exercised: the Frøya A08 test batch returned 4 scripts, 3 valid and 1 rejected for
`heals` / `prevents` / `treat`.

## scripts.json shape

`DESIGN.md` names the artifact but not its fields, so `schema.py` defines them, driven by what the
consumers need. Agent 4 needs one renderable unit per script (avatar brief, ordered beats with
voiceover and on-screen direction, duration). Agent 5 checks audio sync, avatar/demographic match,
product visibility and first-frame scroll-stop — so `avatar_brief`, `product`, `hook` and
`first_frame` are each addressable on their own rather than buried in prose.

Strategy accepted this contract as **provisional**: ship it, Producer reviews before Agent 4 is
built, and it changes then if it needs to. It is not settled, and it does not need to be — revising
it later costs nothing.

## What we pitch

Strategy's position, which bounds what these scripts may claim:

> We never promise performance or medical outcomes. We sell creative volume and angle coverage.

The brand's own unsubstantiated claims stay in `Do not say` and are rejected mechanically. Our pitch
carries the same restraint.
