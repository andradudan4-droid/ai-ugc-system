"""Render a cached brand pull into brand.md (docs/DESIGN.md §3, Agent 0).

brand.md is the per-client half of Agent 3's input -- it pairs with angles.json, so it carries what
a scriptwriter needs to write in the brand's voice about real products, and nothing else.
"""

from __future__ import annotations

import collections
import csv
import datetime as dt
import pathlib
import re

from .sites import load

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "brands"
TARGETS = ROOT / "data" / "targets.csv"

# Actives worth naming in a script -- a hook usually leads with one of these.
INGREDIENTS = [
    "hyaluronic acid", "niacinamide", "retinol", "retinal", "vitamin c", "peptide", "ceramide",
    "salicylic acid", "glycolic acid", "lactic acid", "azelaic acid", "squalane", "collagen",
    "centella", "cica", "panthenol", "bakuchiol", "tretinoin", "benzoyl peroxide", "zinc",
    "vitamin e", "shea butter", "jojoba", "rosehip", "argan", "aloe", "caffeine", "spf",
    "mandelic acid", "tranexamic acid", "snail mucin", "propolis", "urea", "allantoin",
]

# Language that turns a cosmetic into an unapproved drug claim. Surfaced so the scriptwriter has a
# do-not-say list rather than discovering it in review.
CLAIM_RISK = [
    "cure", "cures", "heal", "heals", "treat", "treats", "treatment for", "prevents",
    "eliminates", "permanently", "fda approved", "fda-approved", "clinically proven",
    "doctor recommended", "antibacterial", "anti-bacterial", "reverses", "guaranteed results",
]


def _find(terms: list[str], text: str) -> list[str]:
    low = text.lower()
    return [t for t in terms if re.search(rf"\b{re.escape(t)}\b", low)]


def _ads_row(domain: str) -> dict | None:
    if not TARGETS.exists():
        return None
    for r in csv.DictReader(open(TARGETS)):
        if r["website"].replace("https://", "").rstrip("/") == domain:
            return r
    return None


def _money(p: str) -> float | None:
    try:
        return float(p)
    except (TypeError, ValueError):
        return None


def render(domain: str, today: dt.date | None = None) -> pathlib.Path:
    today = today or dt.date.today()
    raw = load(domain)
    if not raw:
        raise SystemExit(f"no cached pull for {domain} -- collect it first (see intake/README.md)")

    home = raw.get("home", {})
    prods = raw.get("products", {})
    items = prods.get("items", [])
    ads = _ads_row(domain)

    all_copy = " ".join([home.get("description", ""), " ".join(home.get("headings", [])),
                         home.get("body_sample", "")] + [i["body"] for i in items])

    brand = (home.get("site_name") or ads and ads["brand"] or domain.split(".")[0].title()).strip()
    prices = [p for p in (_money(i["price"]) for i in items) if p]
    types = collections.Counter(i["type"] for i in items if i["type"])
    ing = _find(INGREDIENTS, all_copy)
    risks = _find(CLAIM_RISK, all_copy)
    recent = sorted((i["created"] for i in items if i["created"]), reverse=True)[:1]

    L = []
    A = L.append
    A(f"# {brand}")
    A("")
    A(f"- **Site:** https://{domain}")
    A(f"- **Collected:** {today.isoformat()} (Agent 0 / Intake)")
    if prods.get("vendor"):
        A(f"- **Vendor string:** {prods['vendor']}")
    A(f"- **Catalogue:** {prods.get('n', len(items))} published products"
      + (f", {len(items)} captured" if prods.get("n", 0) > len(items) else ""))
    if prods.get("source"):
        A(f"- **Product data source:** {prods['source']}")
    if prices:
        A(f"- **Price range:** ${min(prices):.2f}–${max(prices):.2f} "
          f"(median ${sorted(prices)[len(prices)//2]:.2f})")
    if recent:
        A(f"- **Newest SKU published:** {recent[0]}")
    A("")

    A("## Positioning")
    A("")
    A(home.get("description") or "_No meta description on the homepage._")
    A("")
    if home.get("headings"):
        A("Homepage claims, in the brand's own words:")
        A("")
        for h in home["headings"][:8]:
            A(f"- {h}")
        A("")

    A("## Hero products")
    A("")
    if items:
        A("| Product | Type | Price | In stock |")
        A("|---|---|---|---|")
        for i in items[:10]:
            A(f"| {i['title']} | {i['type'] or '—'} | "
              f"{'$' + i['price'] if i['price'] else '—'} | {'yes' if i['available'] else 'no'} |")
        A("")
        lead = next((i for i in items if i["available"] and i["body"]), None)
        if lead:
            A(f"**Lead product copy — {lead['title']}:**")
            A("")
            A(f"> {lead['body'][:400]}")
            A("")
    else:
        A("_No product feed captured._")
        A("")

    if types:
        A(f"**Category mix:** " + ", ".join(f"{t} ({n})" for t, n in types.most_common(6)))
        A("")

    A("## Ingredients to name in script")
    A("")
    A(", ".join(ing) if ing else "_None of the tracked actives appear in public copy._")
    A("")

    A("## Proof points")
    A("")
    if home.get("reviews") or home.get("rating"):
        if home.get("reviews"):
            A(f"- {home['reviews']} reviews cited on site")
        if home.get("rating"):
            A(f"- {home['rating']} / 5 average rating cited on site")
    else:
        A("- _No review count or rating found on the homepage._")
    A("")

    A("## Ads in market")
    A("")
    if ads:
        A(f"- **Segment:** `{ads['segment']}` · fatigue score {ads['fatigue_score']}")
        A(f"- **Active ads:** {ads['ad_count']} · video ads (est.) {ads['ugc_ad_count_est']}")
        A(f"- **Oldest live ad:** {ads['oldest_ad_days']}d · **newest:** {ads['newest_ad_days']}d ago")
        if ads["notes"]:
            A(f"- Notes: {ads['notes']}")
        A("")
        A(f"**The pitch:** newest creative is {ads['newest_ad_days']} days old against "
          f"{ads['ad_count']} ads still running — they are spending but not refreshing.")
    else:
        A("_Not found in data/targets.csv._")
    A("")

    A("## Do not say")
    A("")
    A("Cosmetic claims only — these phrases appear in the brand's own copy but should not be "
      "repeated in paid creative without substantiation:")
    A("")
    if risks:
        for r in sorted(set(risks)):
            A(f"- \"{r}\"")
    else:
        A("- _No drug-claim language found in captured copy._")
    A("")
    A("Standing constraints: no before/after implying permanent change, no disease or "
      "condition-treatment language, no unearned \"dermatologist recommended\".")
    A("")

    A("## Open questions for the client")
    A("")
    A("- Which SKU carries the margin they want volume on?")
    A("- Do they have creator/UGC footage rights already, or is this net-new?")
    A("- Which of the currently-running ads is their best performer?")
    A("- Any claims legal has already rejected?")
    A("")

    slug = domain.replace(".", "-")
    d = OUT / slug
    d.mkdir(parents=True, exist_ok=True)
    p = d / "brand.md"
    p.write_text("\n".join(L))
    return p
