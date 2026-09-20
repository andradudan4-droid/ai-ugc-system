# AI UGC Agent System — Design

**Date:** 2026-09-19
**Status:** Design approved, pending spec review

## 1. Business model

Creative-as-a-service for DTC brands. We sell ad creative (scripts first, rendered video second).
We do **not** post on client accounts, run their ad accounts, or manage a creator roster in v1.

Rationale: the distribution layer is where all platform risk lives (TikTok's ~15–25 posts/day/account
API cap, C2PA synthetic-media detection, duplicate-content throttling, the ban ladder). Selling
creative keeps that risk with whoever posts, and is the only version sellable before the render
layer exists.

**Category: beauty / skincare.** Chosen for advertiser density, visual demo-ability, and the absence
of regulated health claims (supplements would require an extra compliance agent in v1).

## 2. Core design principle

> Deterministic orchestration, agentic steps.

The pipeline order is plain code. Each *step* is an agent. Every agent writes a structured artifact
to disk — never chat output.

This buys:
- **Resumability** — a 200-render batch with 30 failures resumes, it doesn't restart
- **Attribution** — every asset traces back to the angle and hook that produced it
- **Swappability** — any single agent can be replaced without touching the rest

The anti-pattern being avoided: one large agent that "does the campaign" and cannot be debugged
when it drifts.

## 3. Agent architecture

| # | Agent | Input | Output artifact | Cadence |
|---|-------|-------|-----------------|---------|
| −1 | Prospector | Category | `targets.csv` | Weekly |
| 0 | Intake | Brand URL, product | `brand.md` | Per client, once |
| 1 | Ad miner | Category + competitor list | `hooks.jsonl` | Weekly, parallel fan-out |
| 2 | Taxonomist | `hooks.jsonl` | `angles.json` | Weekly |
| 3 | Scriptwriter | `brand.md` + `angles.json` | `scripts.json` | Per batch |
| 4 | Render queue | Approved scripts | MP4 files | Per batch — *not an agent* |
| 5 | QA | Rendered MP4 | pass/fail + reason, auto-requeue | Per video |
| 6 | Feedback | Client performance data | Reweighted `angles.json` | Monthly |

### Agent −1 — Prospector
Scrapes the same ad library as Agent 1, filtered for **buying signals** rather than hooks:
- Running 15+ UGC-style video ads → believes in UGC, has budget
- Same creatives live 60+ days with nothing new shipped → creative fatigue
- Ad count declining month-over-month → struggling for volume

### Agent 1 — Ad miner
Filters competitor ads to **30+ days running** as a profitability proxy: an ad still live after a
month is paying for itself. This corpus is the actual product; video generation is a commodity
API call layered on top.

**Constraint:** Meta's official Ad Library API covers political/issue ads only. Commercial ads are
UI-only. Agent 1 must use a paid ad-intel API (Foreplay / Atria / adlibrary.com) or computer-use
against the UI. Do not build a Meta scraper — it breaks constantly and violates their ToS.

### Agent 5 — QA
AI video has a 20–40% reject rate. At $4–11 per clip a vision-model QA gate pays for itself
immediately. Checks: audio sync, avatar/demographic match to brief, product visibility, first-frame
scroll-stop, visual artifacts.

## 4. The key asset

`hooks.jsonl` is keyed by **category, not by client.**

Mining 40 skincare brands produces a corpus that serves every skincare client we ever sign, and
improves with each one. Changing category resets it to zero. That is why category is locked early.

### What the corpus is reliable for — revised 2026-09-20

The original spine of this product was "unclaimed angles": telling a brand what nobody in its
category is running. **That thesis failed testing and is withdrawn as a headline claim.**

Measured: **11 of 13 absence-shaped claims were falsified** once probed against the live ad index.
Nine "unclaimed angles" resolved to zero verified-absent, two thin positional gaps, and seven
already claimed. This is not variance — it is the structure of the claim. An absence claim cannot
be confirmed by more evidence, only fail to be contradicted, and a single keyword search can kill it.

**The corpus is reliable for presence and unreliable for absence.** Sell accordingly:

| Sell | Do not sell |
|------|-------------|
| What the category *is* running, with concentration shown | "Nobody is doing X" |
| **Durability** — which openings survive, and how long | Verified absence of any kind |
| Positional divides (who opens on what, and who doesn't) | Gaps we cannot explain |
| What a client already owns and under-runs | |

### Durability is the compounding asset

Every ad carries `days_running`, and the corpus is already filtered to 30+ days because an ad still
running is paying for itself. That signal was used as an inclusion rule and then discarded.

Rank angles by median and maximum survival. This answers a better question than absence — *what
actually works here* — and it is positive, confirmable, and improves monotonically with every brand
mined. It cannot be falsified by one search.

### The natural-owner test

Before any positional gap is called an opportunity:

> Identify the brand with the strongest possible claim to the angle. Do they open on it? If not,
> the absence is probably a verdict the market already reached, not a gap it overlooked.

Worked example: `water_quality` looked unclaimed. eskiin sells a water filter — its entire product
is water quality — and across 390 ads still opens on outcome, demoting filtration to sentence two.
The natural owner declined the position. That is evidence the position does not work.

A genuine gap requires explaining *why everyone else is wrong*. If we cannot, we do not sell it.

### Known sampling bias

The corpus is built from DTC challenger brands. Incumbents (CeraVe, Dove, Eucerin, SkinCeuticals)
are absent by construction, so **positions held by incumbents will read as empty.** The
dermatologist-as-ally angle failed exactly this way. State this limit in every deliverable's method
section.

### Probing is mandatory

No angle may carry an absence or positional verdict that has not been probed against the live index.
Unprobed resolves to `unknown`, and `unknown` never reaches a client document.


## 5. Compounding loop

One pipeline run yields three outputs:

1. `targets.csv` → outbound prospect list
2. `hooks.jsonl` → client deliverable
3. the same teardown → social content

Output 3 feeds a TikTok/short-form account posting about ad creative and category teardowns. That
audience is composed of brand owners and marketers — i.e. the client base. This is lead-gen as a
by-product of work already being done, not a separate content business.

**Time allocation:** outbound is the engine (client in 2–4 weeks); content is the compounding
side-effect (inbound in 4–6 months). Not the reverse.

## 6. Execution approach — hybrid

- **Phase B (now):** run agents 0→3 manually inside GPT-6 Astra using the Arcads MCP and saved
  playbook prompts. Zero build time.
- **Phase A (as volume justifies):** pipeline-as-code — repo, per-stage functions, SQLite state
  table, runs headless on a schedule.

Critical constraint: **Phase B writes the same artifact formats Phase A will read** (`brand.md`,
`hooks.jsonl`, `angles.json`, `scripts.json`). Manual work becomes seed data, not throwaway.

## 7. Tooling

| Tool | Role |
|------|------|
| Claude Code | Build the repo; own agents 0, 2, 3, 5, 6 |
| GPT-6 Astra | Phase B console; Agent 1 computer-use scraping (holds the Arcads MCP) |
| Antigravity | `agy` + Manager view for Agent 1 fan-out **only** — defer until that fan-out is measurably slow |

## 8. Build order

1. **Days 1–2** — lock category, build `targets.csv` (~100 brands)
2. **Days 3–4** — run agents 0→3 on the 5 best targets. No video yet.
3. **Day 5** — ~$50 rendering 3 finished videos for the single best target (brand-specific demo reel)
4. **Week 2** — outreach. Expected funnel: 100 prospects → ~5 replies → 1–2 calls → 1 client
5. **Weeks 2–3** — build the repo around what was learned; add agents 4 + 5
6. **Later** — agent 6, once a client supplies performance data

## 9. Economics

**Generation cost per video:** Creatify ~$3.90/30s · Seedance 2.5 ~$6.50/30s · Arcads ~$11
(Arcads API requires the custom Pro plan.)

**First deal target:** $1–2k/month for ~30 creatives. Cost ~$120. The margin is not the point at
this stage — the case study is.

**Parallel channel:** pitch agencies rather than brands. They hold clients already, need creative
volume, require no education, and have budget today. Lower rate per creative, far higher volume,
no client management.

## 10. Open decisions

- Ad-intel data source for agents −1 and 1 (paid API vs computer-use) — decide before building Agent 1
- Render provider for Agent 4 (cost vs realism tradeoff) — decide before Phase A
- Whether to run the agency channel in parallel from week 1

## 11. Explicitly out of scope for v1

- Posting to any account (client's or our own)
- Creator roster recruitment and payouts
- Paid media management
- Multi-category hook corpus
