"""Agent 1 collection contract.

IMPORTANT -- like prospector/adlibrary.py, this module issues no network requests, by design.
docs/DESIGN.md §3 and CLAUDE.md forbid building a Meta Ad Library scraper. This module owns the
*queries* and the *parser*; a supervised operator opens the URLs and drops captured JSON into
data/raw/ads/. Everything downstream is offline computation over that cache.

SCOPE LIMIT -- read before using. The Ad Library card exposes ad-level metadata (id, start_date,
display format, whether a video is attached) and the ad's *primary text*. It does NOT expose the
spoken or on-screen opening of the video, which is what hooks.jsonl calls hook_text. Obtaining
that means pulling the video asset and transcribing it. That is a separate capability with a
materially different ToS posture and it has not been approved -- see docs/DESIGN.md §10, which
lists the Agent 1 data source as an open decision. So this contract deliberately stops at
metadata + primary text, and hooks.py refuses to guess the rest.
"""

from __future__ import annotations

import pathlib
from urllib.parse import quote  # noqa: F401  (kept for parity with prospector contract)

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADS = ROOT / "data" / "raw" / "ads"

BASE = "https://www.facebook.com/ads/library/"
COUNTRY = "US"


def advertiser_url(page_id: str) -> str:
    """Active video ads for one advertiser -- the creative Agent 1 cares about."""
    return (
        f"{BASE}?active_status=active&ad_type=all&country={COUNTRY}"
        f"&view_all_page_id={page_id}&media_type=video"
    )


# Extends the Agent -1 extractor with the fields Agent 1 needs per ad: the ad's primary text and
# the media handles. Runs inside the already-open tab against the page's own hydrated payload.
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
    if (!pid) continue;
    out.push({
      ad_id: id,
      page_id: pid,
      page_name: g(s, /"page_name":"((?:[^"\\]|\\.)*)"/),
      start_date: Number(g(s, /"start_date":(\d+)/)) || null,
      end_date: Number(g(s, /"end_date":(\d+)/)) || null,
      is_active: /"is_active":true/.test(s),
      // the ad's primary text -- NOT the video's spoken/on-screen opening
      primary_text: g(s, /"body":\{"text":"((?:[^"\\]|\\.)*)"/),
      title: g(s, /"title":"((?:[^"\\]|\\.)*)"/),
      display_format: g(s, /"display_format":"([A-Z_]+)"/),
      has_video: /"video_(?:hd|sd)_url":"http/.test(s),
      collation_count: Number(g(s, /"collation_count":(\d+)/)) || 1
    });
  }
  return out;
})()
"""

SCROLL_JS = """
(async () => {
  for (let i = 0; i < %d; i++) {
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(r => setTimeout(r, 1800));
  }
  return document.body.innerText.match(/~?[\\d,]+\\s+result/)?.[0] ?? null;
})()
"""


def scroll_js(scrolls: int = 8) -> str:
    return SCROLL_JS % scrolls


def is_cached(page_id: str) -> bool:
    return (ADS / f"{page_id}.json").exists()
