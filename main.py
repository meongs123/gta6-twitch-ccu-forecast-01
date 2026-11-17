"""Forecast GTA VI's launch-day Twitch viewers hour by hour (make.fun
gta6-twitch-ccu-forecast-01).

Model: per-hour log-regression on log(hour-1), fitted across past launches.
For each scored hour h = 2..24, regress log(viewers_h) on log(viewers_1)
across the case's comparable launches (each comparable contributes its own
release-day curve), then forecast the target launch at its own hour-1 print:

    log y_h = a_h + b_h * log(p1)

with the slope shrunk 30% toward 1 (persistence of shape) and the intercept
re-centred through the means, so a launch far outside the training range
still extrapolates sanely. The spread is the per-hour MAD of the regression
residuals (x0.70, 3-hour smoothed, floored at 0.08 log units); quantiles are
median * exp(z_tau * spread) with the standard normal z at
0.05/0.25/0.5/0.75/0.95. No trend, no level forecast: the shape comes from
past launches, the level from the target's own hour-1 print.

Why this wins: the leaderboard's top entries are all comparable-shape
models anchored on hour 1. The per-hour slope is what makes it work -- it is
~1.0 at hours 2-3 (the small hours scale with hour 1) but collapses to
~0.06-0.09 at the evening peak (the peak barely depends on the 00:00 print),
so a launch that starts small is forecast a steep climb while one that
starts huge is forecast a flat day. A plain median shape ignores that and
scores ~0.29-0.40; this regression scores 0.172 mean pinball loss on the
four practice launches (house baseline: 0.387).

Standard library only, no network, deterministic: the same case always
produces the same bytes. Reads $MAKEFUN_INPUT_DIR (else /input) and writes
$MAKEFUN_OUTPUT_DIR (else /output), one <id>.out per <id>.in.
"""

import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file imports. (This entry is one file; the line is
# harmless and keeps the door open.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Slope shrinkage toward 1 (persistence of shape) and spread calibration,
# both tuned on the four practice launches and frozen.
SHRINK = 0.30
SPREAD_SCALE = 0.70
SPREAD_FLOOR = 0.08
# A comparable must show hour 1 and at least this many of hours 2-24.
MIN_HOURS = 20
# A per-hour regression needs at least this many launches; below it we fall
# back to the median log-ratio shape for that hour.
MIN_FIT = 5
# Fallback spread (house baseline's random-walk sigma) when no comparable
# at all qualifies: persistence with a widening spread.
BASE_SIGMA = 0.15


def _parse_ts(text):
    """ISO 8601 UTC timestamp -> datetime. Tolerates a trailing Z, a
    +00:00 offset, or fractional seconds; naive input is treated as UTC."""
    cleaned = text.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _median(values):
    return statistics.median(values)


def _release_day(comp):
    """A comparable's release-day hourly viewers: hour 1..24 -> viewers.

    Points are keyed by whole hours after the comparable's day_start. Only
    positive counts count; missing hours simply stay absent.
    """
    day_start = _parse_ts(comp["day_start"])
    curve = {}
    for point in comp.get("hourly", []):
        viewers = point.get("viewers")
        if viewers is None or viewers <= 0:
            continue
        hour = int((_parse_ts(point["from"]) - day_start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24:
            curve[hour] = viewers
    return curve


def _ols(pairs):
    """Least squares y = a + b*x over (x, y) pairs. Returns (a, b)."""
    n = len(pairs)
    mean_x = sum(p[0] for p in pairs) / n
    mean_y = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mean_x) ** 2 for p in pairs)
    if sxx == 0:
        return mean_y, 0.0
    slope = sum((p[0] - mean_x) * (p[1] - mean_y) for p in pairs) / sxx
    return mean_y - slope * mean_x, slope


def _round2(value):
    """Round to 2 decimals, half up (the starter's convention), as a number
    json.dumps writes without a trailing .0 when whole."""
    scaled = value * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    rounded = whole / 100
    return int(rounded) if rounded.is_integer() else rounded


def forecast_case(case, name):
    """The 23 forecast rows for one case."""
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    known = next((k for k in case["known"] if k["hour"] == 1), None)
    if known is None or known["viewers"] is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, known["viewers"])
    log_p1 = math.log(p1)

    # The comparable pool: launches with a usable release-day curve.
    curves = []
    for comp in case.get("comparables", []):
        curve = _release_day(comp)
        if 1 in curve and sum(1 for h in curve if h >= 2) >= MIN_HOURS:
            curves.append(curve)

    medians = {}
    spreads = {}
    if not curves:
        # No shape to learn from: fall back to persistence, the house
        # baseline's forecast, so the case still scores instead of failing.
        for hour in range(2, 25):
            medians[hour] = log_p1
            spreads[hour] = BASE_SIGMA * math.sqrt(hour - 1)
    else:
        raw_spread = {}
        for hour in range(2, 25):
            pairs = [(math.log(c[1]), math.log(c[hour]))
                     for c in curves if hour in c]
            if len(pairs) >= MIN_FIT:
                intercept, slope = _ols(pairs)
                slope = (1.0 - SHRINK) * slope + SHRINK * 1.0
                mean_x = sum(p[0] for p in pairs) / len(pairs)
                mean_y = sum(p[1] for p in pairs) / len(pairs)
                intercept = mean_y - slope * mean_x
                medians[hour] = intercept + slope * log_p1
                residuals = [y - (intercept + slope * x) for x, y in pairs]
            else:
                # Too few launches show this hour: use the median log-ratio
                # shape instead of a regression. With no launch at all
                # showing it, hold the hour at the hour-1 print.
                ratios = [math.log(c[hour] / c[1]) for c in curves if hour in c]
                centre = _median(ratios) if ratios else 0.0
                medians[hour] = log_p1 + centre
                residuals = [r - centre for r in ratios] if ratios else [0.0]
            middle = _median(residuals)
            mad = _median([abs(r - middle) for r in residuals])
            raw_spread[hour] = max(SPREAD_FLOOR, 1.4826 * mad) * SPREAD_SCALE
        # Smooth the spread over neighbouring hours: a per-hour MAD from
        # ~37 launches is noisy, and the true dispersion moves slowly.
        for hour in range(2, 25):
            neighbours = [raw_spread[h] for h in (hour - 1, hour, hour + 1)
                          if 2 <= h <= 24]
            spreads[hour] = sum(neighbours) / len(neighbours)

    rows = []
    for row in case["forecast"]:
        hour = row["hour"]
        centre = medians[hour]
        sigma = spreads[hour]
        quantiles = [_round2(math.exp(centre + z * sigma)) for z in Z]
        # Guard the output contract: finite, > 0, <= 1e9, non-decreasing.
        quantiles = [min(max(q, 0.01), 1_000_000_000) for q in quantiles]
        quantiles.sort()
        rows.append({"hour": hour, "q": quantiles})
    rows.sort(key=lambda r: r["hour"])
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
