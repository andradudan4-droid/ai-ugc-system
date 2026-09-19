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

## Status: built against a fixture

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

This contract is proposed, not agreed — Producer consumes it and has not reviewed it.
