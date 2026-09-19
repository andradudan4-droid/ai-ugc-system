"""Brand-site collection contract for Agent 0.

Same split as Agent -1: this module owns the URLs and the in-page extractors, a browser operator
opens them and drops the captured JSON into data/raw/intake/, and rendering is offline. These are
public storefront surfaces on the brand's own site -- /products.json is Shopify's documented
storefront endpoint, served publicly to any visitor.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "intake"

PRODUCT_LIMIT = 20


def products_url(domain: str) -> str:
    return f"https://{domain}/products.json?limit=250"


def home_url(domain: str) -> str:
    return f"https://{domain}/"


# Run on a /products.json page. Trims each product to what a scriptwriter needs.
PRODUCTS_JS = """
(() => {
  const d = JSON.parse(document.body.innerText);
  return {
    n: d.products.length,
    vendor: (d.products[0] || {}).vendor || '',
    items: d.products.slice(0, %d).map(p => ({
      title: p.title,
      type: p.product_type || '',
      tags: (p.tags || []).slice(0, 8),
      price: (p.variants && p.variants[0] || {}).price || '',
      available: (p.variants || []).some(v => v.available),
      created: (p.created_at || '').slice(0, 10),
      body: (p.body_html || '').replace(/<[^>]*>/g, ' ').replace(/\\s+/g, ' ').trim().slice(0, 300)
    }))
  };
})()
""" % PRODUCT_LIMIT

# Run on the brand homepage. Captures positioning language and on-page proof.
HOME_JS = r"""
(() => {
  const m = n => (document.querySelector(`meta[name="${n}"],meta[property="${n}"]`) || {}).content || '';
  const txt = document.body.innerText.replace(/\s+/g, ' ');
  const heads = [...document.querySelectorAll('h1,h2')]
    .map(h => h.innerText.trim()).filter(Boolean).slice(0, 14);
  const rev = txt.match(/([\d,]+)\+?\s*(?:verified\s+)?(?:reviews|ratings)/i);
  const stars = txt.match(/([0-5][.,]\d)\s*(?:\/\s*5|stars?|out of 5)/i);
  return {
    title: document.title,
    description: m('description') || m('og:description'),
    site_name: m('og:site_name'),
    headings: heads,
    reviews: rev ? rev[1] : '',
    rating: stars ? stars[1] : '',
    body_sample: txt.slice(0, 2500)
  };
})()
"""


def save(domain: str, payload: dict) -> pathlib.Path:
    RAW.mkdir(parents=True, exist_ok=True)
    p = RAW / f"{domain.replace('.', '_')}.json"
    existing = json.loads(p.read_text()) if p.exists() else {}
    existing.update(payload)
    p.write_text(json.dumps(existing, indent=2))
    return p


def load(domain: str) -> dict:
    p = RAW / f"{domain.replace('.', '_')}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def cached_domains() -> list[str]:
    if not RAW.exists():
        return []
    return [p.stem.replace("_", ".") for p in sorted(RAW.glob("*.json"))]
