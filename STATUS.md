# Orbit Wars — Session Status

## TL;DR

Three agents in the repo. The clean rewrite (`main.py`) is roughly tied with
`v26.py` in head-to-head (50% wr at n=24). **Ship `v26.py` as `main.py`** —
it already has the aim convergence fix on top of `v14.8` (which is what's
currently on the ladder at 878 ELO) and is the lowest-risk upgrade.

## What was done this session

1. **Recovered context.** Read `STATUS_after_v28.md` (prior session notes).
   `v28` referenced in that doc was never committed to the repo, so the
   strongest agent available is `v26.py` (3428 lines).

2. **Wrote a clean rewrite from scratch** (`main.py`, 700 lines) using the
   real engine code as reference. Highlights:
   - **Linear-T-search aim solver** with engine-equivalent swept-pair hit
     verification (the prior aim returned non-verified guesses that often
     went off-board).
   - **Off-by-one fix in planet position prediction**: empirically verified
     that at `obs.step=K` the planet is at `theta0 + ang_vel*(K-1)`, not `(K)`.
     My code originally used `(K + future_t)` — one tick ahead of reality.
     Fixed to `max(0, step + future_t - 1)`.
   - Per-planet timeline simulation for defense reservation (matches the
     engine's combat math: top-vs-second, ties annihilate).
   - Distance-scaled chunky fleets, light proactive defense.

3. **Built a local validation harness** (`run_validation.py`) with seeded
   environments and Wilson CIs.

4. **Head-to-head benches (n=24 vs v26):**

| Variant | Description | Wins / Losses | Winrate |
|---------|-------------|---------------|---------|
| `main` v1 | Initial clean agent (no aim verification, no off-by-one fix) | 6 / 6 | 50% |
| `main` v2 | + heavier defense (baseline=3×prod, stacked-window) | 3 / 9 | 25% |
| `main` v3 | + swept-pair aim verification (off-by-one still wrong) | 4 / 8 | 33% |
| `main` v4 | + off-by-one fix | 12 / 12 | **50%** |

The clean rewrite is **competitive but not clearly better** than v26.

5. **Tried `submission_v26plus.py`** = v26 with comet up-weight (`COMET_VALUE_MULT`
   0.65→1.50). Preliminary: 0W/2L vs v26. The down-weight was deliberate;
   over-chasing comets exposes planets. Recommended to NOT ship.

## Why the clean rewrite didn't win decisively

v26 has many sophisticated, well-tuned strategic features that take days to
replicate and tune:
- Snipe missions (intercept enemy attacks on neutrals)
- Multi-source coordinated swarm (2- and 3-source attacks on hostile planets)
- Crash exploit (4P-specific)
- Gang-up missions (post-battle clean-up)
- Rescue / recapture for my planets
- Reinforce to hold
- Elimination missions for weakest enemy
- Total-war endgame
- Doomed planet evacuation
- Rear forwarding

The clean rewrite captures the **core 70%** (planning, defense, capture
sizing, aim correctness) in 1/5 the line count. With another full session it
could close the gap; for now, v26 is the safer ship.

## Concrete next steps to push toward top-10

1. **Submit `v26.py`** as `main.py` to Kaggle. Estimated ladder lift: +50 to
   +100 ELO vs v14.8 (based on STATUS_after_v28.md's report of v20c at 62%
   wr vs v14.8 — v26 has the same structure with the aim convergence fix).

2. **(Parallel)** Submit `main.py` (clean v4) too. Kaggle rates the latest 2.
   Ladder data will tell us if the cleaner aim verification is worth the
   missing strategic features.

3. **Backport `main.py`'s swept-pair aim verification + off-by-one fix into
   `v26.py`** as v26.1. The off-by-one might exist there too (v26's
   `predict_planet_position` uses `cur_ang` from current position which
   should be correct, but worth checking). Single-line change with potentially
   measurable lift.

4. **Implement v29-A from `STATUS_after_v28.md` properly:** comet anticipation.
   Not just a value multiplier — actually pre-position fleets in each
   quadrant in anticipation of spawn at steps 49 / 149 / 249 / 349 / 449.
   This is the biggest unimplemented structural improvement.

5. **Sweep instrumentation + offensive sweep parking** (v29-B from STATUS).
   Drop fleets in front of orbiting planets so the planet sweeps into the
   fleet — free combat without travel cost.

6. **Combat-aware target reservation in v26's `is_target_saturated`.** v26
   currently only checks defender; should also check if an enemy fleet in
   flight would tie/beat our incoming under top-vs-second math.
