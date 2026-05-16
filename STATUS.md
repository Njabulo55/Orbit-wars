# Orbit Wars — Session Status

## TL;DR — what to ship

**`main.py` = v27** (committed and pushed).

Local n=24 vs v26: **15W / 9L = 62.5% (Wilson CI ~42-79%)**.

That's the strongest improvement signal we've gotten this session. Submit it.

```bash
kaggle competitions submit orbit-wars -f main.py -m "v27: v26 + kingmaker + aim safety"
```

## What changed in v27

Two targeted additions on top of v26 (research-report prioritized):

1. **Kingmaker logic for 4P games.** v26 always preferred attacking the
   weakest enemy. v27 instead attacks the *leader* when I'm behind
   (`_kingmaker_mode`), with a 1.7× target value multiplier on the leader's
   planets. Activates only when I'm 4P and leader_score > my_score × 1.10.
   The "weakest while a leader is running away" mistake is the classic
   kingmaker failure mode and v26 had it baked in.

2. **Aim path safety (OOB + sun rejection).** Wraps v26's iterative
   `aim_with_prediction`. After it returns, verify the flight path stays
   on board and doesn't cross the sun. If invalid, fall back to
   `search_safe_intercept` and re-verify. If both fail, return None — the
   agent skips the target instead of launching a doomed fleet.
   *Intentionally loose* — only OOB and sun are rejected, NOT strict swept-pair
   hit. We measured a 25% wr regression with strict swept-pair before
   loosening, because v26's iterative aim often converges 1-2 units off
   but the engine's target-radius tolerance still catches the hit.

## What the head-to-head benches said

| Variant | vs v26 (n, steps, actTO) | Winrate | Decision |
|---------|--------------------------|---------|----------|
| `main` v1 (clean rewrite) | 12, 500, 10 | 6W / 6L = 50% | shelved |
| `main` v2 (heavier defense) | 12, 500, 10 | 3W / 9L = 25% | regressed, reverted |
| `main` v3 (aim verify, off-by-one bug) | 12, 500, 10 | 4W / 8L = 33% | regressed |
| `main` v4 (off-by-one fixed) | 16+8, 300, 1 | 12W / 12L = 50% | competitive |
| `v27` (= v26 + kingmaker + aim safety) | 16+8, 150, 1 | **15W / 9L = 62.5%** | **ship** |
| `submission_v26plus.py` (v26 + comet upweight) | 2 only, then bench stalled | 0W / 2L | abandon |

The clean rewrite (`main.py` v4) is technically solid but doesn't
out-perform v26 because it's missing v26's tuned strategic features
(snipe, swarm, gang-up, rescue, recapture, reinforce, crash-exploit,
weakest-enemy targeting, total-war endgame). Replicating those was
not feasible in this session.

## Current ladder context

- `v14.8` (the prior submission): **878 ELO**.
- Newer v26-class submission: **6W / 3L over 9 games** per user = 67% wr,
  still converging.
- Leaderboard #1: **~1600 ELO**.
- Target: **2000 ELO** (user's stated goal for a competitive top-10 slot).

A 67% wr submission typically converges around 1100-1300 ELO depending on
opponent pool. v27 is +12.5pp (= +50-100 ELO) on top of that, so ladder
estimate is **1150-1400 ELO** range. Not 2000 yet — see next steps.

## Why we're not at 2K yet, and how to get there

v26 (and v27) is a tuned, heuristic-based scripted agent. The research
report's analysis applies directly:

> "Rules-based agents with smart pruning win in the short term, but RL
> with good self-play wins given enough training time."

Getting from ~1200 to 2000 ELO needs structural advantages, not more tuning.
Concrete next steps, ranked by expected EV:

### Highest EV (next session)

1. **Forward-rollout plan evaluation (MCTS-lite).**
   After `plan_moves` builds the move list, project forward 20-25 turns
   for two plans: (a) v26 default, (b) defense-priority (drop top 2
   highest-send attacks). Pick whichever has better
   `my_projected_total - max(enemy_projected_total)` at horizon.
   *Why this is high EV:* v26 is greedy. Sometimes the top mission
   leaves us vulnerable. Forward look-ahead catches this without rebuilding
   the whole planner.

2. **Sweep parking offense.** The engine sweeps orbiting planets through
   their arc each tick using `swept_pair_hit` between fleet and planet
   segments. A fleet parked on the predicted arc gets attacked BY the
   moving planet — free combat with no travel cost. v26 doesn't exploit
   this. Implementation: for each orbiting enemy planet, compute its
   sweep envelope for the next 10-20 turns. Find points reachable by our
   fleets that lie on the envelope. Launch.

3. **Proper comet anticipation (v29-A from STATUS_after_v28.md).**
   Pre-position fleets at step 49/149/etc. toward where comets will spawn
   in our quadrant. Currently v26 only reacts to comets *after* spawn,
   which means racing the opponent. Pre-positioning wins the race for
   free 1-production planets that compound for the rest of the game.

4. **Opponent aggression model.** Track per-opponent fleet launch volume
   over rolling 20-turn windows. Adapt: tighter defense vs aggressors,
   faster expansion vs turtles. v26's `MEMEX_ARCHIVE` was a stub for
   exactly this and was never wired into the planner. Implementation
   is a small `world.opponent_aggression[owner]` field + a defense ratio
   multiplier in `build_policy_state`.

### Long-term (multi-session, GPU helpful)

5. **AlphaZero-style MCTS with learned value/policy network.** PPO
   self-play. Replaces random rollouts with a value function. Polar
   coordinate state encoding `(r, θ, dθ/dt)` per planet. Action masking
   to prune illegal/dominated actions. Per the report, this approach has
   never won a Kaggle simulation comp yet — meaning there's open space.

6. **Behavior cloning from top-bot replays.** Kaggle exposes episode
   replays via API. Train a supervised imitation policy on the current top-10's
   behavior, fine-tune with PPO. Faster cold-start than pure RL.

7. **Graph neural network for planet/fleet topology.** Better fit than
   CNN/MLP for variable-entity dynamic graphs.

## Files in the repo

```
main.py                         # = v27, the submission
v27.py                          # explicit v27 copy
v26.py                          # baseline (Tamrazov+Ykhnkf hybrid w/ aim conv fix)
submission_v26plus.py           # v26+comet-upweight (regressed, abandoned)
run_validation.py               # seeded h2h harness with Wilson CIs
README.md                       # submission guide
STATUS.md                       # this file
STATUS_after_v28.md             # prior-session notes
```

## Sanity asks before next session

* Confirm v27 actually beats the current submitted bot on the ladder
  after a few hundred games. Lower-bound expectation: +50 ELO.
* If v27 underperforms there but won the local bench, the difference
  is *opponent pool* — v27 might be overfit to v26-style opponents.
  Re-test against starter/random agents to verify breadth.
* Decide whether to spend the next session on the forward-rollout MCTS
  (highest near-term EV) or start the RL training pipeline (highest
  long-term EV).
