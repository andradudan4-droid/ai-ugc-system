# AI UGC Agent System — Build Repo

## What this session is for

Building the system. Execution only.

Strategy, business model, pricing, category choice and scope changes are decided in a separate
conversation. They are **not** open questions here.

## Operating rules

1. **Build, don't discuss.** No strategy proposals, no alternative business models, no
   re-litigating decisions in `docs/DESIGN.md`.
2. **Read `docs/DESIGN.md` first.** It is the source of truth. If a task appears to contradict
   it, say so in one line and stop — do not resolve it yourself.
3. **One agent at a time**, in the order given. Do not build ahead.
4. **Every agent writes a file.** Structured artifacts on disk — never chat output as a deliverable.
   Artifact formats in `docs/DESIGN.md` §3 are contracts; do not change them without being told.
5. **Report in outcomes.** What was built, whether it runs, what it produced, what is blocked.
   No progress narration.
6. **Blocked is a valid answer.** If something can't be done (API access, ToS limits, missing
   credentials), say so plainly and stop. Do not improvise a workaround that creates platform risk.

## Hard constraints

- **Do not build a Meta Ad Library scraper.** Meta's official API covers political/issue ads only.
  Use public browsable surfaces or a paid ad-intel API. Nothing that violates platform ToS.
- **Do not build anything that posts to social accounts.** Out of scope for v1 (`docs/DESIGN.md` §11).
- **Do not spend money on render APIs** without being told explicitly. Generation costs $4–11/video.

## Build order

| Step | Deliverable | Status |
|------|-------------|--------|
| 1 | Agent −1 (Prospector) → `targets.csv`, 100 skincare brands | **done** (105 rows) |
| 2 | Agent 0 (Intake) → `brand.md` | **done** (top 5 fatigued) |
| 3 | Agent 1 (Ad miner) → `hooks.jsonl` | **done (pilot)** — 113 hooks, 5 of 81 brands; copy-derived openings |
| 4 | Agent 2 (Taxonomist) → `angles.json` | **done (pilot)** — 14 angles, 9 saturated, 9 unclaimed |
| 5 | Agent 3 (Scriptwriter) → `scripts.json` | **current** (Writer) |
| 6 | Agent 4 (Render queue) + Agent 5 (QA) | not started |
| 7 | Agent 6 (Feedback) | not started |

Update the status column as steps complete.
