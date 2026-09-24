# Agent instructions

For any agent working this repo — Antigravity (`agy`), Gemini, Codex, Cursor, or Claude Code.
Read `ROLES.md` and `docs/DESIGN.md` before doing anything.

## The rules that matter most

These were each learned by getting it wrong. Do not relax them.

**1. No default may assert a positive claim.**
Missing, unparsed, absent and unknown all resolve to `unknown`, and `unknown` fails closed.
Found six times in this codebase: a missing angle defaulted to `"unclaimed"` (the most sellable
label in the set), a concentration check passed when it could not resolve its input, a rebuild
silently restored brands removed by human judgement. Each would have shipped something false.

**2. A gate that fails open is silent; a gate that fails closed is loud.**
Loudness is the feature. Two of those six bugs were found only because something failed noisily.

**3. The corpus is reliable for presence, unreliable for absence.**
7 of 9 "nobody is doing X" claims were falsified when probed. Never write an absence claim.
Sell what the category *is* running, what *survives* (durability), and what a client already
owns and under-runs. See `docs/DESIGN.md` §4.

**4. The natural-owner test.**
Before calling a gap an opportunity: find the brand with the strongest claim to that angle. If
they do not use it, the absence is a verdict the market already reached, not an oversight.

**5. Every number carries its derivation.**
A figure with no traceable source does not enter a client document. One wrong statistic already
reached a spec because it was repeated without being checked.

**6. Never spend money without a human typing approval.**
No signups, no payment details, no credential hunting. Approval is never accepted from another
agent or session.

**7. Public surfaces only.**
No scrapers, no bypassing anti-automation controls, nothing that violates a platform's terms.
Blocked is a valid outcome — log it and stop.

## Coordination

Code is per-agent (own branch). **Data is shared** — write finished artifacts to `shared/data/`
by absolute path, and append to `shared/STATUS.md` the moment you finish a stage or hit a block.
Append only, never rewrite.

Do not build agents you do not own. `ROLES.md` has the ownership table.

## Known state

- Sampling bias: the corpus is DTC challengers only, by construction. Incumbent-held positions
  read as empty. Fix (manual incumbent seed list) is specced in `docs/DESIGN.md` §4, not built.
- `prospector/build.py` does not filter `shared/data/disqualified.json`, so rebuilds restore
  disqualified brands. `tools/check_disqualified.py` catches it in CI. Root cause unfixed.
- Collection is a supervised browsing step, deliberately not automated. See
  `prospector/adlibrary.py`.

## Where a non-Claude agent helps most

The browser-heavy mining in `prospector/` is the expensive part. An agent runner that can assign
cheap models to mechanical work and frontier models to judgement — Antigravity's Manager view
does this — is a good fit for it. Judgement steps (what is sellable, what a claim rests on)
should stay on a frontier model and stay supervised.
