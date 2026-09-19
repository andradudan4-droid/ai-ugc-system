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
