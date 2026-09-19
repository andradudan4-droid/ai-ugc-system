"""Meta Ad Library collection contract for Agent -1.

IMPORTANT -- this module issues no network requests to Meta, by design.

docs/DESIGN.md §3 and CLAUDE.md forbid building a Meta Ad Library scraper. So the division of
labour is: this module owns the *queries* (which Ad Library URLs to open) and the *parser* (a
snippet of JS that reads the already-rendered page), and a browser operator -- an agent driving
the built-in browser tools, or a human with devtools -- opens those URLs and drops the captured
JSON into data/raw/. Everything downstream (prospector/build.py) is pure local computation over
that cache, so reruns are offline and free.

Re-collection is therefore an explicit, supervised step rather than an unattended crawler.
"""

from __future__ import annotations

import json
import pathlib
from urllib.parse import quote

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DISCOVERY = RAW / "discovery"
ADVERTISERS = RAW / "advertisers"
SNAPSHOTS = RAW / "snapshots"

BASE = "https://www.facebook.com/ads/library/"
COUNTRY = "US"

# Category seed queries. Agent -1 discovers advertisers by searching the ad copy that skincare
# brands actually write, rather than from a hand-maintained brand list.
SEED_QUERIES = [
    "hyaluronic acid serum", "vitamin c serum", "retinol cream", "niacinamide serum",
    "acne treatment", "dark spots", "fine lines and wrinkles", "skin barrier",
    "korean skincare", "gentle cleanser", "face moisturizer", "eye cream",
    "peptide serum", "spf moisturizer", "azelaic acid", "salicylic acid",
    "collagen cream", "glowing skin", "anti aging serum", "hydrating toner",
    "clean skincare", "dermatologist tested", "skincare routine", "sunscreen face",
    "pore minimizer", "under eye bags", "hyperpigmentation", "rosacea redness",
]


def search_url(query: str, media_type: str = "all") -> str:
    """Keyword search over ad copy -- used for advertiser discovery."""
    return (
        f"{BASE}?active_status=active&ad_type=all&country={COUNTRY}"
        f"&q={quote(query)}&search_type=keyword_exact_phrase&media_type={media_type}"
    )


def advertiser_url(page_id: str, media_type: str = "all") -> str:
    """All active ads for one advertiser. media_type='video' isolates their video creative."""
    return (
        f"{BASE}?active_status=active&ad_type=all&country={COUNTRY}"
        f"&view_all_page_id={page_id}&media_type={media_type}"
    )


# Runs inside the already-open Ad Library tab and returns one record per rendered ad. It reads the
# page's own hydrated payload -- the same data the cards display -- and normalises the escaped JSON
# before matching. Fields map 1:1 onto what build.py needs.
EXTRACT_JS = r"""
(function(){
  const H = document.documentElement.innerHTML.replace(/\\"/g,'"').replace(/\\\//g,'/');
  const parts = H.split('"ad_archive_id":"');
  const g = (s, re) => { const m = s.match(re); return m ? m[1] : null; };
  const seen = new Set(); const out = [];
  for (let i = 1; i < parts.length; i++) {
    const s = parts[i];
    const id = s.slice(0, s.indexOf('"'));
    if (seen.has(id)) continue; seen.add(id);
    const pid = g(s, /"page_id":"?(\d{6,})"?/);
    const pname = g(s, /"page_name":"((?:[^"\\]|\\.)*)"/);
    if (!pid || !pname) continue;
    out.push({
      ad_id: id, page_id: pid, page_name: pname,
      start_date: Number(g(s, /"start_date":(\d+)/)) || null,
      end_date: Number(g(s, /"end_date":(\d+)/)) || null,
      is_active: /"is_active":true/.test(s),
      caption: g(s, /"caption":"((?:[^"\\]|\\.)*)"/),
      link_url: g(s, /"link_url":"((?:[^"\\]|\\.)*)"/),
      display_format: g(s, /"display_format":"([A-Z_]+)"/),
      has_video: /"video_(?:hd|sd)_url":"http/.test(s),
      collation_count: Number(g(s, /"collation_count":(\d+)/)) || 1
    });
  }
  return out;
})()
"""

# Scroll to pull in more cards before extracting (the grid lazy-loads ~30 at a time).
SCROLL_JS = """
(async () => {
  for (let i = 0; i < %d; i++) {
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(r => setTimeout(r, 1800));
  }
  const t = document.body.innerText.match(/~?[\\d,]+\\s+result/);
  return t ? t[0] : null;
})()
"""


def result_count_js(scrolls: int = 0) -> str:
    return SCROLL_JS % scrolls


def save(kind: str, key: str, payload) -> pathlib.Path:
    """Cache a raw pull. kind is 'discovery' | 'advertisers' | 'snapshots'."""
    d = {"discovery": DISCOVERY, "advertisers": ADVERTISERS, "snapshots": SNAPSHOTS}[kind]
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    p = d / f"{safe}.json"
    p.write_text(json.dumps(payload, indent=2))
    return p


def load_all(kind: str) -> dict:
    d = {"discovery": DISCOVERY, "advertisers": ADVERTISERS, "snapshots": SNAPSHOTS}[kind]
    if not d.exists():
        return {}
    return {p.stem: json.loads(p.read_text()) for p in sorted(d.glob("*.json"))}


def is_cached(kind: str, key: str) -> bool:
    d = {"discovery": DISCOVERY, "advertisers": ADVERTISERS, "snapshots": SNAPSHOTS}[kind]
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return (d / f"{safe}.json").exists()
