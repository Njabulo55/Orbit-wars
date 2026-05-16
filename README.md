# Orbit Wars — Submission Candidates

## Current state on Kaggle ladder

`v14.8` — **878 ELO** (the agent in production). Has a known aim-convergence bug
that produces ~60-85% off-board fleets on non-converged shots.

## Candidates in this branch

| File | Description | Local h2h vs v26 (n=24) | Recommended? |
|------|-------------|--------------------------|--------------|
| `v26.py` | The Tamrazov+Ykhnkf hybrid with the aim-convergence fix. ~3400 lines of strategic features (snipe, swarm, gang-up, rescue, recapture, reinforce, crash-exploit, weakest-enemy targeting, total-war endgame). STATUS_after_v28.md describes this tier as ~62% vs v14.8. | (baseline) | **Yes — most predictable upgrade vs v14.8.** |
| `submission_v26plus.py` | v26 + `COMET_VALUE_MULT 0.65→1.50`. Up-weights comets as capture targets. Preliminary local data shows it's losing to v26 — the down-weight in v26 was deliberate (avoiding over-chase). | _losing 0W/2L early_ | No — abandon |
| `main.py` | **Clean rewrite (v4)** — 700 lines, exact-math aim solver (swept-pair verified, off-by-one corrected), per-planet timeline simulation for defense reservation. Easier to iterate on but missing v26's strategic features. | 12W/12L = 50% | Experimental |

## How to submit

```bash
# Recommended — ship v26 unmodified (has aim convergence fix on top of v14.8):
cp v26.py main.py
kaggle competitions submit orbit-wars -f main.py -m "v26 (aim convergence fix)"

# Experimental — clean rewrite as a parallel track:
kaggle competitions submit orbit-wars -f main.py -m "Clean rewrite v4 (experimental)"
```

Kaggle accepts up to 5 submissions per day, with ratings of the latest 2 tracked.
The user can run **both** in parallel — Kaggle will rate them separately. That
gives ladder data on whether the clean rewrite holds up against real opponents
(not just v26 in local self-play).

## What's still in `main.py` worth keeping

1. **Swept-pair aim verification** — every aim is checked against the engine's
   collision math; off-board paths and sun-crossing paths are rejected.
2. **Off-by-one fix in planet prediction** — at `obs.step=K`, the planet is at
   `theta0 + ang_vel*(K-1)`, not `(K)`. Empirically verified.
3. **Per-planet timeline simulation** — combat-aware defense reservation
   (similar to v26 but simpler).
4. **Linear T-search aim** — no oscillating fixed-point; one pass over candidate
   arrival turns with explicit hit verification.

These could be back-ported into v26 if we have time — should reduce v26's
off-board fleet rate further.

## Next moves to push toward top-10

1. **Ship v26+comet now** to get fresh ladder data. ELO should converge over 1-2 days.
2. **Backport `main.py`'s swept-pair aim verification into v26** as v26.1.
3. **Add proper comet anticipation** (not just up-weight): pre-position fleets in
   each quadrant near step 49 in anticipation of spawn. This is v29-A from
   `STATUS_after_v28.md`; expected to be the largest structural gain.
4. **Sweep awareness** — instrument and exploit orbiter sweep captures.
5. **Combat-aware target reservation** — check whether enemy fleets en-route to
   our target would tie/beat ours under top-vs-second math, and skip if so.
