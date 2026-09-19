"""Agent 1 output stage: ad records -> hooks.jsonl.

Deliberately source-agnostic. Whatever the open decision in docs/DESIGN.md §10 lands on -- a paid
ad-intel API or a supervised browser pull -- the records get normalised here, so this stage is not
invalidated by that choice. Callers adapt their source to AdRecord; this module owns the contract,
the 30+ day filter and the integrity rule.

INTEGRITY RULE -- hook_text is never inferred, paraphrased or generated.

Two things can legitimately fill it, and they are NOT interchangeable, so every row carries a
hook_source saying which it is:

  transcribed       the video's spoken/on-screen first 1-3s. What the spec means. Needs a source
                    that supplies transcripts -- still undecided, docs/DESIGN.md §10.
  ad_copy_opening   the opening of the ad's primary text, off the public Ad Library card.
                    Available today at zero cost, but it is the caption above the video, not the
                    scroll-stopper in it. Observed example (eskiin, 128d live): "eskiin will give
                    you your best skin & hair - guaranteed." That is a product claim, not a hook.

Copy-derived openings are opt-in (allow_copy_derived=True) so the choice is explicit and Agent 2
can filter on hook_source rather than inheriting a silent mix.

hooks.jsonl is the category asset (docs/DESIGN.md §4) and its 'unclaimed angles' derivative is
sold to clients. A hook that no brand actually ran is worse than a missing one: it is a confident
lie that propagates through Agent 2 into client deliverables. So an ad whose real opening was
never captured is written to the pending sidecar, not to hooks.jsonl.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import pathlib
import re

MIN_DAYS_RUNNING = 30  # docs/DESIGN.md §3: profitability proxy -- still live after a month


@dataclasses.dataclass
class AdRecord:
    """One ad as captured from whichever source is approved."""
    brand: str
    ad_id: str
    start_date: int | None              # unix seconds
    is_active: bool = True
    display_format: str | None = None
    has_video: bool = False
    primary_text: str | None = None     # caption copy -- NOT the hook
    hook_text: str | None = None        # spoken/on-screen first 1-3s. Transcribed, or absent.
    end_date: int | None = None

    def days_running(self, now: int) -> int | None:
        if not self.start_date:
            return None
        until = self.end_date if (self.end_date and not self.is_active) else now
        return max(0, (until - self.start_date) // 86400)


def _fmt(rec: AdRecord) -> str:
    if rec.has_video or (rec.display_format or "").upper() in {"VIDEO", "DCO"}:
        return "video"
    if (rec.display_format or "").upper() in {"DPA", "CAROUSEL"}:
        return "carousel"
    return "image"


def _copy_opening(text: str | None) -> str | None:
    """First sentence of the ad's primary text -- its opening, not a summary."""
    if not text or not text.strip():
        return None
    first = text.strip().split("\n", 1)[0].strip()
    m = re.match(r"(.{10,180}?[.!?])(?:\s|$)", first)
    return (m.group(1) if m else first)[:180].strip() or None


def build(records: list[AdRecord], now: int | None = None,
          allow_copy_derived: bool = False) -> tuple[list[dict], list[dict]]:
    """Return (hooks, pending).

    hooks   -- ads 30+ days live with a hook_text, each tagged with its hook_source.
    pending -- ads 30+ days live with no usable opening at all. The work backlog, not a defect.

    allow_copy_derived=False (default) admits only transcribed openings.
    """
    now = now or int(dt.datetime.now(dt.timezone.utc).timestamp())
    hooks, pending = [], []

    for r in records:
        days = r.days_running(now)
        if days is None or days < MIN_DAYS_RUNNING:
            continue  # younger than the profitability threshold, or undateable
        base = {
            "brand": r.brand,
            "days_running": days,
            "ad_id": r.ad_id,
            "format": _fmt(r),
        }
        text, source = (r.hook_text or "").strip(), "transcribed"
        if not text and allow_copy_derived:
            text, source = _copy_opening(r.primary_text) or "", "ad_copy_opening"
        if text:
            hooks.append({
                "brand": r.brand,
                "hook_text": text,
                "hook_source": source,
                "hook_type": None,   # assigned by Agent 2
                "format": base["format"],
                "angle": None,       # assigned by Agent 2
                "days_running": days,
                "ad_id": r.ad_id,
            })
        else:
            pending.append({**base, "reason": "no transcribed opening captured",
                            "primary_text": r.primary_text})
    return hooks, pending


def write_jsonl(rows: list[dict], path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return path
