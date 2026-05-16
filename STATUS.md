# Orbit Wars — Current State

## What's in the repo

| File | Purpose |
|------|---------|
| `main.py` | New clean agent (v30 / v3). Simulation-driven planner, swept-pair-verified aim, comet bonus. ~700 lines. |
| `v26.py` | Prior session's best — the Tamrazov+Ykhnkf hybrid with aim convergence fix. ~3400 lines. **Not on the ladder.** |
| `run_validation.py` | Local h2h harness with seeded envs and Wilson CIs. |
| `STATUS_after_v28.md` | Prior-session notes (recommended shipping v28; v28 code was never committed). |

## Currently submitted on Kaggle

**v14.8** — `878 ELO`. This is described in `STATUS_after_v28.md`; its source has the OOB / aim-convergence bug (60-85% off-board rate on non-converged shots).

## Local validation so far (n=12, 500 steps, seeded)

| Challenger | vs v26 | Notes |
|------------|--------|-------|
| main v1 (initial) | **6W/6L = 50%** CI [25–75] | Cleaner code, simpler strategy |
| main v2 (heavier defense) | 3W/9L = 25% CI [9–53] | Over-reserved → couldn't expand |
| **main v3 (aim verified + comet bonus + v1 defense)** | _in progress_ | Current head |

vs **starter agent** (1v1 sanity): **8W/0L** for v3.

## Key findings

1. **The clean agent isn't clearly better than v26.** At ~50% wr vs v26, shipping it instead of v26 gives no improvement.
2. **Heavy defense is harmful.** The 25% wr at v2 came from `baseline = 3*prod` choking expansion. Reverted.
3. **Aim solver had bugs.** Original `main.py` used a wide tolerance band that approved off-board paths. v3 now verifies hits using the engine's swept-pair geometry. This is a real correctness improvement.
4. **Comets, snipe, gang-up, swarm — all missing in main.py.** v26 has them; replicating each is substantial work.

## Strategic options for top-10

**Option A — Ship v3 to Kaggle now.** Clean codebase, aim correctness improvement. Risk: roughly tied with v26 in local h2h, so unclear lift vs v14.8.

**Option B — Backport the swept-pair-verified aim into v26 and ship that.** Single targeted change to a strong base. Lowest risk, predictable improvement.

**Option C — Add v29-A comet anticipation to v26 and ship.** Per `STATUS_after_v28.md`, this is the biggest expected structural gain (~5-10% wr).

**Option D — Iterate on main.py: add snipe/swarm/gang-up.** Several days of work to match v26's tuning; uncertain timeline.

My recommendation: **B + C combined**, packaged as `submission.py` derived from `v26.py`. That gives a tuned strategic base + the off-board fix + the unimplemented comet structural improvement. Predictable +5-10% on `v14.8`'s ELO baseline.
