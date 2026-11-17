[![make.fun](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/meongs123/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/meongs123/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

# GTA VI launch-day Twitch viewers, hour by hour

Entry by **meongs123** for the [make.fun bounty](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
"Forecast GTA VI's launch-day Twitch viewers hour by hour" ($250 USDC, 20 places).

`main.py` (Python 3.13, standard library only) reads each case's `<id>.in`
and writes `<id>.out` with five quantiles (0.05/0.25/0.5/0.75/0.95) of the
Twitch category's concurrent viewers for hours 2–24 of the release day,
anchored on the case's hour-1 print.

## The winning pattern (read off the live leaderboard)

Every entry in the top 10 forecasts a **shape, not a level**: the median is
the hour-1 print times an hourly ratio learned from past launches
("Comparable-Shape Forecaster — OLS on Log Hour-1", rank 1 at 0.169;
"local-linear log-ratio model", rank 2 at 0.180; "similarity-weighted
comparables", rank 6 at 0.204; "Nearest-15 launch-shape", rank 11 at 0.226).
Nobody up there predicts a level or a trend — the launch-day curve is a
shape that past launches already traced, and the only thing the target
contributes is its own hour-1 print, which sets the scale. The pay line
(rank 10) sits at ~0.225 mean pinball loss; the house baseline
(persistence, every hour = hour 1) scores ~0.387 and pays nothing. The
decisive detail inside the shape is that the per-hour slope on log(hour-1)
is ~1.0 in the small hours but collapses to ~0.06–0.09 at the evening peak:
a launch that starts small climbs steeply all day, one that starts huge
stays flat — a plain median shape misses that and scores ~0.29–0.40, while
the per-hour regression scores 0.172 on the same four practice launches.

## Model

For each scored hour h = 2..24, ordinary least squares of log(viewers_h)
on log(viewers_1) across the case's comparable launches (each comparable
contributes its own release-day curve; a launch qualifies with hour 1
present and at least 20 of hours 2–24):

    log y_h = a_h + b_h * log(p1)

- The slope is shrunk 30% toward 1.0 and the intercept re-centred through
  the means, so a target outside the training range still extrapolates
  sanely (the largest comparable hour-1 print is ~875k viewers).
- The spread is the per-hour MAD of the regression residuals
  (1.4826 × MAD, floored at 0.08 log units), scaled ×0.70 and smoothed
  over neighbouring hours; quantiles are median × exp(z_tau × spread)
  with z = −1.645/−0.674/0/0.674/1.645. The ×0.70 is calibrated, not
  guessed: the residual distribution is light-tailed, so the honest 90%
  band is narrower than a normal-with-MAD-sigma band (practice coverage
  0.880 at ×0.70, 0.913 at ×0.75, 0.946 at ×1.0).
- Fallbacks keep every case valid: an hour with fewer than 5 launches
  uses the median log-ratio shape; with no usable comparable at all the
  entry falls back to persistence with the house baseline's widening
  spread. No network, no randomness, deterministic — two runs on the
  same case are byte-identical.

What was tried and dropped: a plain median shape (0.285–0.396), Huber
regression (no gain over OLS), a second regressor from pre-release hype
(max/mean viewers in the 24–48h before release — correlation with the
evening peak only 0.06–0.12, no gain), hour-1 channels (no gain),
similarity-weighted OLS and k-NN shape (unstable: great on one launch,
terrible on the next), and asymmetric empirical quantiles (the residuals
are skewed upward, but per-hour empirical tails are too noisy and cost
0.03). The final model is the plain per-hour OLS with slope shrinkage
and a calibrated MAD spread.

## Validation (local, practice cases p00–p03)

Practice answers are SullyGnome's "Average viewers" for the four launch
days (hours 2–24), scored with the exact pinball rule from RULES.txt.
The scorer reproduces the house baseline exactly (loss 0.387097, typical
miss 82.75%, 90% coverage 0.783 — RULES.txt says ~0.387 / ~82.8% /
~0.783), so the numbers below are on the same scale as the leaderboard.

| case | loss | typical miss | 90% coverage |
| ---- | ---- | ------------ | ------------ |
| p00 Marvel's Wolverine | 0.1610 | 21.85% | 0.870 |
| p01 Red Dead Redemption 2 | 0.1593 | 23.87% | 0.913 |
| p02 God of War Ragnarök | 0.1337 | 16.24% | 0.957 |
| p03 Marvel's Spider-Man 2 | 0.2340 | 43.45% | 0.783 |
| **mean** | **0.1720** | **25.95%** | **0.880** |

House baseline on the same cases: mean loss 0.3871, miss 82.75%,
coverage 0.783. The entry beats the baseline by 0.215 and sits below
the rank-10 pay line (~0.225) and just above rank 1 (0.169) on the live
practice board — i.e. paid territory if the final launch behaves like
the practice launches.

Leave-one-launch-out (train on the case's 37 comparables plus the other
three practice launches' release-day curves, test the held-out launch —
the final's pool is 42 comparables): mean loss **0.1658**. Dropping any
single comparable moves the p00 loss only between 0.1525 and 0.1785, so
no one launch drives the result.

Runtime ~0.15 s per case (limit 8 s); outputs deterministic
(byte-identical across runs) and 4/4 valid.

## Files

- `main.py` — the entry (one file, standard library only)
- `README.md` — this file
- `LICENSE` — MIT
- `CHANGES.md` — one short note per build round
- `.makefun/owner.json` — payout wallet
