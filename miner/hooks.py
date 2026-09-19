"""Agent 1 output stage: ad records -> hooks.jsonl.

Deliberately source-agnostic. Whatever the open decision in docs/DESIGN.md §10 lands on -- a paid
ad-intel API or a supervised browser pull -- the records get normalised here, so this stage is not
invalidated by that choice. Callers adapt their source to AdRecord; this module owns the contract,
the 30+ day filter and the integrity rule.

INTEGRITY RULE -- hook_text is never inferred, paraphrased or generated.

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


def build(records: list[AdRecord], now: int | None = None) -> tuple[list[dict], list[dict]]:
    """Return (hooks, pending).

    hooks   -- ads 30+ days live WITH a real transcribed hook_text. Ready for hooks.jsonl.
    pending -- ads 30+ days live whose opening was never captured. These are the work backlog,
               not a defect: they are what the approved data source still has to supply.
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
        if r.hook_text and r.hook_text.strip():
            hooks.append({
                "brand": r.brand,
                "hook_text": r.hook_text.strip(),
                "hook_type": None,   # assigned by Agent 2
                "format": base["format"],
                "angle": None,       # assigned by Agent 2
                "days_running": days,
                "ad_id": r.ad_id,
            })
        else:
            pending.append({**base, "reason": "hook_text not captured by approved source",
                            "primary_text": r.primary_text})
    return hooks, pending


def write_jsonl(rows: list[dict], path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return path
