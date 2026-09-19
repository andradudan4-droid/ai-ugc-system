# Agent 0 — Intake

Produces `data/brands/<slug>/brand.md`: the per-client half of Agent 3's input (`docs/DESIGN.md` §3).
Cadence: per client, once.

## Run it

```bash
python3 run_intake.py --plan --top 5   # URLs to open for the top 5 `fatigued` targets
python3 run_intake.py                  # re-render every cached brand — offline
```

Same two-phase split as Agent −1: `intake/sites.py` owns the URLs and in-page extractors, a browser
operator opens them and drops JSON into `data/raw/intake/`, and `intake/render.py` writes brand.md
offline from that cache.

## What brand.md carries

Only what a scriptwriter needs: positioning in the brand's own words, hero products with real prices
and stock state, the actives worth naming in a hook, proof points, the current ad situation pulled
from `targets.csv`, and a **Do not say** list built by scanning the brand's own copy for drug-claim
language ("cure", "heals", "treats"). That last section exists so claim problems surface before a
script is written rather than in review.

## Product data provenance

`/products.json` is Shopify's documented public storefront endpoint. Where a brand serves it the
product data is exact and the row says so. Three of the first five did not serve it — SpoiledChild
runs a headless storefront (404), Asarai and Saeskyn do not expose it — so their products come from
the rendered catalogue or homepage rail, and `brand.md` names the source in the header. Prices and
stock state from a rail are less complete than a feed.

## Intake qualifies; the prospector cannot

Agent −1 ranks on ad behaviour alone, which cannot tell a brand from a store that merely runs
skincare ads. Agent 0 visits the site, so it is the first step that can. Rejections go in
`data/disqualified.json` with a reason and Agent −1 reads that file, so a rejected domain does not
climb back up the next weekly run.

Rejected so far:

- **shopellox.com** — redirects to shoppaya.com, a general dropship store (hair clips, foot files,
  curtain rod brackets). Had ranked #2 on ad signals alone.
- **lovi.care** — AI skincare app that recommends *other* brands' products. No own line.

Kept but flagged in its own file: **saeskyn.com** is genuinely skincare, but 24 white-label Korean
SKUs all showing "50% OFF ENDS TODAY", no about page, no reviews and no ingredient library are
dropshipper hallmarks. It scores well and is worth a look, not a first call.
