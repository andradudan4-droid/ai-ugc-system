"""Fatigue scoring for Agent -1 (Prospector).

Ranks beauty/skincare advertisers by how worth pitching they are, using the three
buying signals in docs/DESIGN.md §3.
"""

from __future__ import annotations

import math

# FATIGUE FORMULA -- fatigue_score = 100 * sum(WEIGHTS[k] * component_k), where each component is
# a ratio passed through the saturating curve 1-exp(-1.6*r) (so hitting the threshold scores ~0.8
# and the curve keeps ranking past it instead of flat-topping at 1 and tying the whole front of the
# list): `stale` = newest_ad_days/STALE_FULL (nothing new shipped -> the core fatigue signal),
# `longevity` = oldest_ad_days/LONGEVITY_FULL (same creatives live on), `budget` =
# ugc_ad_count/UGC_BAR (>=15 UGC video ads means they believe in UGC and have budget), `decline` =
# month-over-month drop in ad_count (needs >=2 snapshots, so it is 0 on a first run); the result is
# then multiplied by a gate that zeroes out brands with no active ads and halves brands running no
# video at all. Tune by editing WEIGHTS and the constants below -- nothing else depends on them.

WEIGHTS = {
    "stale": 0.40,
    "budget": 0.30,
    "longevity": 0.20,
    "decline": 0.10,
}

STALE_FULL = 60.0      # days since newest ad that counts as fully fatigued (DESIGN.md: 60+)
LONGEVITY_FULL = 180.0  # days the oldest live ad has run to count as fully entrenched
UGC_BAR = 15.0         # UGC-style video ads that count as "believes in UGC, has budget"
DECLINE_FULL = 0.50    # a 50% month-over-month drop in ad count is a full decline signal

NO_VIDEO_PENALTY = 0.5  # brands running zero video ads are a poor fit for a UGC video offer


SATURATION = 1.6  # shape of the diminishing-returns curve; higher = flattens sooner


def _sat(ratio: float) -> float:
    """Map a 0..inf ratio into 0..1, saturating near 1 without ever tying at the cap."""
    if ratio <= 0:
        return 0.0
    return 1.0 - math.exp(-SATURATION * ratio)


def components(
    ad_count: int,
    ugc_ad_count: int,
    oldest_ad_days: float | None,
    newest_ad_days: float | None,
    prev_ad_count: int | None = None,
) -> dict[str, float]:
    """Return each 0..1 scoring component. `prev_ad_count` is last month's snapshot, if any."""
    stale = _sat((newest_ad_days or 0) / STALE_FULL)
    longevity = _sat((oldest_ad_days or 0) / LONGEVITY_FULL)
    budget = _sat(ugc_ad_count / UGC_BAR)

    if prev_ad_count and prev_ad_count > 0:
        decline = _sat(((prev_ad_count - ad_count) / prev_ad_count) / DECLINE_FULL)
    else:
        decline = 0.0

    return {"stale": stale, "budget": budget, "longevity": longevity, "decline": decline}


def fatigue_score(
    ad_count: int,
    ugc_ad_count: int,
    oldest_ad_days: float | None,
    newest_ad_days: float | None,
    prev_ad_count: int | None = None,
) -> float:
    if ad_count <= 0:
        return 0.0

    c = components(ad_count, ugc_ad_count, oldest_ad_days, newest_ad_days, prev_ad_count)
    raw = sum(WEIGHTS[k] * c[k] for k in WEIGHTS)

    gate = NO_VIDEO_PENALTY if ugc_ad_count == 0 else 1.0
    return round(100 * raw * gate, 2)
