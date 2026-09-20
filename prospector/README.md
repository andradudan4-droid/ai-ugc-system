# Agent −1 — Prospector

Produces `data/targets.csv`: beauty/skincare DTC brands ranked by how worth pitching they are.
Cadence: weekly (`docs/DESIGN.md` §3).

## Run it

```bash
python3 run_prospector.py          # rebuild the CSV from data/raw/ — offline, deterministic
python3 run_prospector.py --plan   # print the Ad Library URLs to re-open for a fresh collection
```

The rebuild reads only `data/raw/` and makes no network calls, so it is free to re-run and the
output is byte-identical for a given cache.

## Two phases

**Collection (supervised, in a browser).** `prospector/adlibrary.py` owns the Ad Library URLs and
`EXTRACT_JS`, a snippet that reads the already-rendered page. A browser operator opens the URLs and
drops the captured JSON into `data/raw/`. Nothing in this repo makes an HTTP request to Meta —
`CLAUDE.md` forbids building an Ad Library scraper, so re-collection stays an explicit, paced,
supervised step rather than an unattended crawler.

**Build (offline).** `brands.py` collapses pages into brands, `score.py` ranks them, `build.py`
writes the CSV and snapshots the run.

## Cache layout

```
data/raw/discovery/*.json        one file per seed keyword search — the candidate advertiser pool
data/raw/candidates.json         deduplicated brands with the page_id to measure
data/raw/advertisers/            per-advertiser ad counts, video counts and ad-age bounds
data/raw/snapshots/<date>.json   ad counts per run — the month-over-month decline baseline
```

## How a brand is identified

Discovery returns Facebook *pages*, not brands, so `brands.py` fixes three things: affiliate pages
("Dr Laura", "Beauty After 50") collapse into the brand whose site they link to; brands that link to
a retailer (Aveeno → amazon.com) are identified by page name instead; and advertisers from other
categories that matched a skincare keyword are dropped.

## Scoring

`score.py` holds the formula in one commented block. Five components — `budget`, `stale`, `volume`,
`longevity`, `decline`. Retune via `WEIGHTS` and the threshold constants; nothing else depends on
their values.

**`stale` is a band, not a monotonic reward.** It is a trapezoid over `newest_ad_days`: zero below
15d, full across 45–120d, decaying to zero by 180d. The spec's signal is "creatives live 60+ days
with nothing new shipped", which assumes the advertiser is *still buying*. A brand silent for 200+
days has stopped advertising rather than fatigued and cannot buy creative, so it scores zero there
and lands in the `dormant` segment.

Volume outweighs staleness (`budget` + `volume` = 0.55 vs `stale` 0.25): volume proves budget,
staleness only times the approach.

`decline` is 0 on a first run — it needs two snapshots at least 21 days apart.

## Segments

| segment | meaning |
|---|---|
| `fatigued` | qualified, 45–120d since newest ad — urgent, lead with these |
| `high_volume` | 50+ UGC ads and shipping within 30d — no urgency, best long-term clients |
| `cooling` | past the fatigue window (120–180d), not yet written off |
| `active` | qualified and shipping, but neither fatigued nor at high_volume's bar |
| `dormant` | 180d+ silent — kept in the file, excluded from outreach |
| `unqualified` | under 15 UGC video ads |

## Category, and the corpus gate

`category` comes from Agent 0 visiting the site, via `data/categories.json`. Values: `skincare`,
`beauty_device`, `fragrance`, `makeup`, `accessory`, `unverified`.

**Only `category == "skincare"` may enter the skincare hook corpus** (`docs/DESIGN.md` §4). That
corpus is the compounding asset; mixing in a filtered showerhead or a silk pillowcase destroys what
makes it valuable. Non-skincare rows stay in `targets.csv` as legitimate prospects — they just get
their own corpus if one is ever taken as a client — and carry an EXCLUDE note so the gate is visible
two ways.

`unverified` means nobody has visited it yet. Those brands surfaced from skincare keyword searches
so they are probably skincare, but on current evidence that guess is wrong often enough to matter:
of 25 brands visited, 5 were disqualified outright and 8 more were in-category beauty but not
skincare. **Roughly half of what ad behaviour ranks highly is not what it looks like.** Intake
before mining.

## What we pitch (Strategy position)

> We never promise performance or medical outcomes. We sell creative volume and angle coverage.

A brand's own claims stay in their `Do not say` and never enter our scripts — Agent 3 enforces that
mechanically. The same restraint applies to our pitch: more creative and better-targeted angles, not
results. This is the honest position and it keeps us out of the regulatory surface `DESIGN.md` §1
chose this category to avoid.

## Structural limit: this discovery method is challenger-biased

Agent −1 finds advertisers by keyword-searching **ad copy**. That surfaces brands buying heavily on
direct response — challenger DTC brands — and under-samples incumbents, who advertise differently
and often on other surfaces. The seed queries in `SEED_QUERIES` are written in challenger language
("dark spots", "skincare routine"), which compounds it.

**Consequence: every downstream corpus built from `targets.csv` will read incumbent-held positions
as empty.** This is not a sampling accident that more brands would fix — it is what the discovery
method selects for.

The worked example cost a real finding. `dermatologist_as_ally` appeared in zero of 139 mined
openings, and Agent 2 reported it as the category's best open position. It is heavily occupied —
Dove, CeraVe, Eucerin, SkinCeuticals and Bio-Oil all open on derm endorsement. The corpus saw only
challengers, who define themselves *against* derm authority, and read the position as vacant.

The fix is not more of the same discovery. Any absence claim drawn from this corpus has to be probed
against the live ad library, and a gap has to pass a **natural-owner test**: find the advertiser with
the strongest claim to the position and check whether they open on it. If the obvious owner will not
touch it, the gap is evidence the position does not sell.

## Known limits

- **Ad Library renders ~30 ads per page and does not paginate for logged-out users.** `ad_count` is
  always the exact figure Meta reports, but for advertisers over ~30 ads `ugc_ad_count` is scaled
  from the 30-ad sample and the ad-age bounds come from that sample, so the true oldest ad may be
  older. Both cases are flagged per row in `notes`. 25 of 108 rows are exact.
- **`ugc_ad_count_est` means "video ads", not verified UGC-style.** It uses Meta's own
  `media_type=video` signal. Separating UGC-style from polished brand video needs a vision pass —
  that is Agent 1's job. The `_est` suffix is because most rows are scaled from a 30-ad sample.
- **`brand` is named after the destination domain unless the page name matches it.** The domain is
  the identity that can be verified and pitched; affiliates advertise under names of their own
  ("jaxandbrynco" runs saltair.com's creative). The cost is that a brand whose page name is good but
  whose domain differs reads as the domain ("Weareluna" for Soluna SKIN). The page name is always
  preserved in `notes` as `advertises as "..."`.
- **US only** (`COUNTRY` in `adlibrary.py`).
