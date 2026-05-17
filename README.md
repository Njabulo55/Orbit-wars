# Orbit Wars — Submission Candidates

## Submitted (ladder)

`v14.8` — 878 ELO baseline. Has aim-convergence bug.
Newer submission (≈v26-class) — early data: 6W/3L over 9 games (67% wr).

## Recommended for next submission: `main.py` (= v27)

**v27 = v26 + kingmaker(4P) + OOB/sun aim safety.**

Local h2h vs v26 over n=24 seeded 1v1 games: **15W/9L = 62.5%** (Wilson CI ≈ 42-79%).

What v27 adds on top of v26 (3535 lines, mostly v26's tuned strategy):

1. **Kingmaker logic for 4P** (`_compute_leader_enemy`, `_kingmaker_mode`). If
   I'm behind the leader (leader_score > my_score × 1.10), bias target value
   toward the LEADER (×1.7) instead of the weakest enemy. Targeting the
   weakest while a runaway leader is forming is a kingmaker mistake — denying
   the leader keeps the game competitive. (Only fires in 4P games.)

2. **Aim path safety** (`_verify_aim_hit`). After v26's iterative
   `aim_with_prediction` returns, verify the path doesn't leave the board or
   cross the sun. If invalid, fall back to `search_safe_intercept` and
   re-verify. Returns None if both fail (so the agent skips the target
   instead of wasting a fleet). The verifier is intentionally loose — it
   does NOT require strict swept-pair hit, just no-OOB and no-sun, because
   v26's iterative aim often converges 1-2 units off but the engine's
   target-radius tolerance still catches the hit; stricter checks throw
   away real opportunities (we measured 25% wr regression with strict
   swept-pair before loosening to OOB+sun only).

## Files

| File | Description |
|------|-------------|
| `main.py` | Production submission — same content as `v27.py` |
| `v27.py` | v26 + kingmaker + aim safety (62.5% wr vs v26) |
| `v26.py` | Tamrazov+Ykhnkf hybrid with aim convergence fix |
| `submission_v26plus.py` | v26 + comet up-weight — regressed in early bench, do not ship |
| `run_validation.py` | Seeded local h2h with Wilson CIs |
| `STATUS.md` | Session log |
| `STATUS_after_v28.md` | Prior-session notes |

## How to submit to Kaggle

```bash
# main.py is already v27. Just submit it:
kaggle competitions submit orbit-wars -f main.py -m "v27: v26 + kingmaker (4P) + aim safety"
```

## Concrete next steps toward 2K ELO

(Per the research report — these are the highest-EV improvements not yet
implemented; each is a substantial session of work.)

### Short-term (next session)

1. **Forward-rollout plan evaluation.** After v26 builds a `missions` list,
   simulate forward 20-25 turns for the default plan AND for a defense-priority
   alternate (drop top 2 attack missions). Pick whichever has best projected
   `(my_total_ships - max_enemy_total_ships)` at the horizon. Expected lift:
   +5-15% wr because v26's greedy mission execution sometimes commits to
   attacks that leave it vulnerable.

2. **Sweep parking offense.** Engine sweeps orbiting planets through their
   arc each tick. Park a fleet on the predicted arc and the planet sweeps
   into you — free combat with no travel cost. v26 doesn't do this offensively.

3. **Proper comet anticipation (v29-A from STATUS_after_v28.md).**
   Pre-position fleets at step 49/149/249/349/449 toward the expected comet
   appearance zone in our quadrant (~30-40 units from sun at angle 2π/3 to
   5π/6 for player 0). Currently v26 only reacts after spawn.

4. **Opponent aggression model.** Track per-opponent fleet launch rate
   over 20-turn windows. If aggressive: tighten defense ratios. If turtling:
   accelerate expansion. (V26's MEMEX_ARCHIVE was stubbed but never wired in.)

### Long-term

5. **MCTS with learned policy/value (AlphaZero-style).** PPO self-play to
   train a value function that evaluates board state and a policy that
   prunes the tree. Expected to dominate scripted agents given training
   time. Needs GPU.

6. **Polar-coordinate state encoding for any RL approach.** The continuous
   orbital geometry is more naturally represented in (r, θ, dθ/dt) than
   Cartesian.

7. **GNN architecture for planet/fleet topology.** Dynamic graph with
   planet nodes (orbit angle, ship count, owner) and fleet edges (in-flight
   ships with arrival ETA). GNN message-passing handles variable entity
   count better than CNNs/MLPs.

## Open issues

* My `predict_planet_position` (in `main.py` and `v27.py` — though both now
  use v26's version) computes future positions from `cur_ang + ang_vel*turns`.
  This is robust to obs.step semantics but I previously found an off-by-one
  bug in the alternative `theta0 + ang_vel*step` formulation. Worth verifying
  v26's version against the engine across more cases.
* The aim verifier is loose (OOB+sun only). A future version could add
  strict swept-pair verification *plus* fall back to a ship-count sweep
  (try ships=20, 50, 100, etc.) when strict verification fails, instead of
  giving up. The earlier strict version caused a regression because it
  rejected without retrying.
