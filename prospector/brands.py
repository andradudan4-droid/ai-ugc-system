"""Turn raw Ad Library discovery rows into a deduplicated candidate brand list.

Discovery returns Facebook *pages*, which is not the same as brands. Three things have to be
fixed up: affiliate pages ("Dr Laura", "Beauty After 50") advertise someone else's product and
should collapse into that brand; big brands link to a retailer (Aveeno -> amazon.com) so their
destination domain is useless as an identity; and skincare keyword searches drag in advertisers
from other categories that have to be dropped.
"""

from __future__ import annotations

import re

# Destination domains that identify a retailer, not the advertiser. For these the brand identity
# comes from the page name instead of the link.
RETAIL_DOMAINS = {
    "amazon.com", "amazon.ca", "amzlink.to", "walmart.com", "target.com", "costco.com",
    "ulta.com", "macys.com", "sephora.com", "instagram.com", "itunes.apple.com",
    "open.spotify.com", "shop.mikmak.ai", "urlgeni.us", "best.lovetoknow.com", "revolve.com",
}

# Out-of-category advertisers pulled in by keyword overlap.
EXCLUDE_DOMAINS = {
    "ninjatransfers.com", "swimzip.com", "harrys.com", "everydaydose.com", "uprootclean.com",
    "rhonutrition.com", "drinkgoodpeels.com", "officialmusclemax.com", "blackgirlvitamins.co",
    "femplus.com", "try.primitivelabsresearch.com", "alevia.com", "discoverycove.com",
    "angel.com", "slickproductsua.com", "nejaticlinic.uk-dental-clinic.co.uk", "mycarpe.com",
    "in.blissy.co", "yoprettyboy.com", "www.yoprettyboy.com",
}
EXCLUDE_NAMES = {
    "whatnot", "fetch", "c4 energy", "runner movie", "figureo pod", "ninja transfers",
    "robert love, brain health expert", "ryan bishop", "usa ready families", "discovery cove",
    "swimzip", "harry's", "meredith hudkins", "sarah lapierre", "melis cifcili",
    "lovetoknow", "ulta beauty", "wellness insider", "jasthetics clinic",
}

# Beauty brands whose ads point at a retailer -- the site we would actually pitch.
BRAND_SITE = {
    "aveeno": "aveeno.com", "cerave skincare": "cerave.com", "l'oreal paris": "lorealparis.com",
    "neutrogena": "neutrogena.com", "biore skincare": "biore.com", "eucerin": "eucerinus.com",
    "shiseido": "shiseido.com", "mederma": "mederma.com", "olay": "olay.com",
    "clinique": "clinique.com", "the ordinary": "theordinary.com", "covergirl": "covergirl.com",
    "amlactin": "amlactin.com", "maree": "mareeglycolicpads.com", "frankly": "franklyskin.com",
    "ulta beauty": "ulta.com", "differin": "differin.com", "roc skincare": "rocskincare.com",
}


def root_domain(caption: str) -> str:
    """Reduce an ad caption to a comparable registrable-ish domain."""
    if not caption:
        return ""
    c = caption.strip().lower()
    c = re.sub(r"^https?://", "", c)
    c = c.split("/")[0].split("?")[0]
    if not c or "." not in c:
        return ""
    # Strip common ad subdomains so join.quiabeauty.com and quiabeauty.com are one brand.
    parts = c.split(".")
    if len(parts) > 2 and parts[0] in {
        "www", "join", "try", "go", "get", "shop", "offer", "quiz", "interview",
        "order", "in", "us", "my", "app", "start", "info", "learn", "news",
    }:
        parts = parts[1:]
    return ".".join(parts)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _titleize(domain: str) -> str:
    stem = domain.split(".")[0]
    stem = re.sub(r"^(try|get|shop|the|official|join)", "", stem)
    return stem.title() if stem else domain


def candidates(discovery: dict[str, dict]) -> list[dict]:
    """Collapse {page_id: [name, caption, ads, vids]} rows from every query into brands."""
    pages: dict[str, dict] = {}
    for rows in discovery.values():
        for pid, row in rows.items():
            name, caption, ads, vids = row[0], row[1], row[2], row[3]
            p = pages.setdefault(pid, {"page_id": pid, "name": name, "captions": {}, "ads": 0, "vids": 0})
            p["ads"] += ads
            p["vids"] += vids
            d = root_domain(caption)
            if d:
                p["captions"][d] = p["captions"].get(d, 0) + ads

    groups: dict[str, dict] = {}
    for p in pages.values():
        if _norm(p["name"]) in {_norm(n) for n in EXCLUDE_NAMES}:
            continue
        doms = sorted(p["captions"], key=lambda d: -p["captions"][d])
        brand_dom = next((d for d in doms if d not in RETAIL_DOMAINS), "")
        if brand_dom in EXCLUDE_DOMAINS:
            continue

        if brand_dom:
            key, website = brand_dom, brand_dom
        else:
            # Retailer-linked or link-less page: identify by page name.
            key = _norm(p["name"])
            website = BRAND_SITE.get(p["name"].strip().lower(), "")
            if not key:
                continue

        g = groups.setdefault(key, {"key": key, "website": website, "pages": [], "ads": 0, "vids": 0})
        g["pages"].append(p)
        g["ads"] += p["ads"]
        g["vids"] += p["vids"]
        if website and not g["website"]:
            g["website"] = website

    out = []
    for g in groups.values():
        # The brand's own page is the one whose name looks like the domain; otherwise the page
        # with the most ads seen. Everything else on the domain is an affiliate.
        dom_stem = _norm(g["website"].split(".")[0]) if g["website"] else ""
        def affinity(p):
            n = _norm(p["name"])
            match = bool(dom_stem) and (n in dom_stem or dom_stem in n)
            return (match, p["ads"])
        primary = max(g["pages"], key=affinity)
        out.append({
            "key": g["key"],
            "brand": primary["name"].strip(),
            "website": g["website"] or "",
            "page_id": primary["page_id"],
            "affiliate_pages": len(g["pages"]) - 1,
            "seen_ads": g["ads"],
            "seen_vids": g["vids"],
        })

    out.sort(key=lambda r: -r["seen_ads"])
    return out
