"""Fatigue scoring and segmentation for Agent -1 (Prospector).

Ranks beauty/skincare advertisers by how worth pitching they are, using the three buying signals
in docs/DESIGN.md §3.
"""

from __future__ import annotations

import math

# FATIGUE FORMULA -- fatigue_score = 100 * sum(WEIGHTS[k] * component_k). `budget`
# (ugc_ad_count/UGC_BAR), `volume` (ad_count/VOLUME_BAR) and `longevity`
# (oldest_ad_days/LONGEVITY_FULL) are ratios through the saturating curve 1-exp(-1.6*r), so hitting
# a threshold scores ~0.8 and the curve keeps ranking past it instead of flat-topping into ties;
# `decline` is the month-over-month drop in ad_count (needs two snapshots >=21 days apart, so it is
# 0 on a first run). `stale` is NOT monotonic -- it is a trapezoid band over newest_ad_days, because
# the spec's signal is "creatives live 60+ days with nothing new shipped", which assumes the
# advertiser is still buying. Past ~STALE_ZERO days of silence a brand has stopped advertising
# rather than fatigued, and cannot buy creative, so the band returns to 0. Volume outweighs
# staleness (0.55 vs 0.25): volume proves budget, staleness only times the approach. Tune via
# WEIGHTS and the constants below -- nothing else depends on their values.

WEIGHTS = {
    "budget": 0.35,     # UGC video volume -- believes in UGC
    "stale": 0.25,      # in the fatigue window
    "volume": 0.20,     # total ad volume -- proves budget
    "longevity": 0.10,  # same creatives entrenched
    "decline": 0.10,    # losing creative volume month over month
}

UGC_BAR = 15.0          # UGC-style video ads that count as "believes in UGC, has budget"
VOLUME_BAR = 50.0       # active ads that count as a serious, continuous buyer
LONGEVITY_FULL = 180.0  # days the oldest live ad has run to count as fully entrenched
DECLINE_FULL = 0.50     # a 50% month-over-month drop in ad count is a full decline signal

# Staleness band over days since the newest ad, as (ramp start, peak start, peak end, zero).
STALE_RAMP = 15.0   # below this they are shipping fine -- no urgency
STALE_PEAK_LO = 45.0
STALE_PEAK_HI = 120.0
STALE_ZERO = 180.0  # at and beyond this, treat as dormant rather than fatigued

SATURATION = 1.6        # shape of the diminishing-returns curve; higher = flattens sooner
NO_VIDEO_PENALTY = 0.5  # brands running zero video ads are a poor fit for a UGC video offer

# Segment thresholds.
QUALIFY_UGC = 15     # below this they have not shown UGC appetite at all
HIGH_VOLUME_UGC = 50  # proven appetite and budget, even with no fatigue urgency
SHIPPING_DAYS = 30    # newest ad this recent means their creative pipeline is healthy


def _sat(ratio: float) -> float:
    """Map a 0..inf ratio into 0..1, saturating near 1 without ever tying at the cap."""
    if ratio <= 0:
        return 0.0
    return 1.0 - math.exp(-SATURATION * ratio)


def _stale_band(days: float | None) -> float:
    """Trapezoid: 0 until STALE_RAMP, 1 across the peak, back to 0 by STALE_ZERO."""
    if days is None or days <= STALE_RAMP or days >= STALE_ZERO:
        return 0.0
    if days < STALE_PEAK_LO:
        return (days - STALE_RAMP) / (STALE_PEAK_LO - STALE_RAMP)
    if days <= STALE_PEAK_HI:
        return 1.0
    return (STALE_ZERO - days) / (STALE_ZERO - STALE_PEAK_HI)


def components(ad_count, ugc_ad_count, oldest_ad_days, newest_ad_days, prev_ad_count=None):
    """Return each 0..1 scoring component. `prev_ad_count` is last month's snapshot, if any."""
    decline = 0.0
    if prev_ad_count and prev_ad_count > 0:
        decline = _sat(((prev_ad_count - ad_count) / prev_ad_count) / DECLINE_FULL)
    return {
        "budget": _sat(ugc_ad_count / UGC_BAR),
        "stale": _stale_band(newest_ad_days),
        "volume": _sat(ad_count / VOLUME_BAR),
        "longevity": _sat((oldest_ad_days or 0) / LONGEVITY_FULL),
        "decline": decline,
    }


def fatigue_score(ad_count, ugc_ad_count, oldest_ad_days, newest_ad_days, prev_ad_count=None):
    if ad_count <= 0:
        return 0.0
    c = components(ad_count, ugc_ad_count, oldest_ad_days, newest_ad_days, prev_ad_count)
    raw = sum(WEIGHTS[k] * c[k] for k in WEIGHTS)
    gate = NO_VIDEO_PENALTY if ugc_ad_count == 0 else 1.0
    return round(100 * raw * gate, 2)


def segment(ad_count: int, ugc_ad_count: int, newest_ad_days: float | None) -> str:
    """Which outreach bucket a brand belongs in.

    Two buckets beyond the four outreach ones: `cooling` sits between fatigued and dormant
    (past the peak window, not yet silent long enough to write off), and `active` is the residual --
    qualified and shipping, but neither fatigued nor at high_volume's bar.
    """
    if ad_count <= 0 or ugc_ad_count < QUALIFY_UGC:
        return "unqualified"
    if newest_ad_days is not None and newest_ad_days >= STALE_ZERO:
        return "dormant"
    if newest_ad_days is not None and STALE_PEAK_LO <= newest_ad_days <= STALE_PEAK_HI:
        return "fatigued"
    if newest_ad_days is not None and newest_ad_days > STALE_PEAK_HI:
        return "cooling"
    if ugc_ad_count >= HIGH_VOLUME_UGC and newest_ad_days is not None and newest_ad_days <= SHIPPING_DAYS:
        return "high_volume"
    return "active"
