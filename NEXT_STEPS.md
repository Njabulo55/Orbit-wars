# Next-Session Plan: Beyond Heuristics

## The ceiling problem

Per the user's observation:
> "if it's at a grandmaster level, we won't see it lose as much in the first
> few games until it starts struggling around 1.5-2K"

We're seeing the opposite — v27 went 7/12 = 58% on the ladder, consistent with
local 62.5% vs v26. That's a heuristic agent at the upper-end of pure-script
performance. Without learning or deeper search, ~1200-1400 ELO is the ceiling.

Top-10 / 2K ELO requires moving beyond hand-tuned scoring functions.

## What v28 does (this session — ship today)

**Forward-simulation plan evaluation (MCTS-lite).** After v26's greedy planner
produces a move list, project the outcome at horizon T=20 turns. Try dropping
the last 1-3 moves (lowest-priority by execution order). If any alternate
plan has better `(my_total - max_enemy_total)` projection, use it.

This is the smallest possible step beyond heuristics: we evaluate plans by
*simulated consequence*, not just *summed score*. Real ELO impact uncertain
until ladder data lands.

## Next session — three paths in priority order

### Path A: Real MCTS with engine-step rollout (~4-6 hours)

Goal: 1-ply minimax with engine-accurate rollouts.

1. **Game-state simulator** (~2 hours). Extract `interpreter` logic from
   the engine into a pure-Python replayable simulator: takes (planets, fleets,
   step, [action_p0, action_p1]) → returns next state. We don't need to import
   the full kaggle env — just the combat/movement/rotation/spawn logic.

2. **MCTS over move bundles** (~2 hours). At each turn, generate K=4-6
   candidate move bundles (= v27's plan with different mission-filter
   policies: default, defense-priority, aggressive, conservative).
   For each, run rollout: 8-12 turns of self-symmetric play (both sides
   use v27's planner against the simulated state). Score by terminal
   `my_total - max_enemy_total`. Pick the highest-scoring bundle.

3. **Action masking** (~1 hour). During rollout, prune obvious losers:
   moves that send ships to a planet already projected to be captured by us,
   moves whose ship count would tie an incoming enemy (annihilation),
   moves into the sun.

Expected lift: +10-20% wr vs v27 if implemented well. The forward-search
is what every classical strong agent has — Halite, Kore, Lux all used it.

### Path B: Behavior cloning from top-bot replays (~3-5 hours)

Goal: bootstrap a learned policy from competitive replays.

1. **Replay fetcher** (~1 hour). Use Kaggle API:
   ```bash
   kaggle competitions episodes <top_submission_id>
   kaggle competitions replay <episode_id>
   ```
   Pull 100-500 episodes from the top-10 bots. Each replay is JSON with
   per-step observations and actions.

2. **State encoder** (~1 hour). Polar coordinates per planet:
   `(r, theta, dtheta_dt, ships, production, owner_one_hot, is_comet)`.
   Pad/mask to max-planet-count (~40). Same shape for fleets:
   `(r, theta, ships, dest_r, dest_theta, eta, owner_one_hot)`.

3. **Small policy network** (~2 hours). PyTorch (need to `pip install torch` —
   available, no GPU but CPU works for small nets):
   - Set-transformer or simple MLP over entity features
   - Output: per-source-planet head producing
     `(target_planet_softmax, send_fraction_in_[0,1])`
   - Train via supervised cross-entropy on (state, action) pairs from replays

4. **Hybrid agent** (~1 hour). Use the network's top-K predictions as
   candidate moves, then verify each through v27's combat-math before
   committing. (Action correction layer.)

Expected lift: depends on replay quality and overfitting. Could be +20-40%
wr if the top bots are doing things we can't reverse-engineer with rules.

### Path C: Full PPO self-play (~overnight + multiple sessions)

Goal: train a value/policy network from scratch via self-play.

1. **Gym-style env wrapper** (~2 hours). Wrap the engine as a single-agent
   gym env where the opponent is a frozen agent (initially v27).

2. **Polar coordinate observation** + entity-attention policy (~3 hours).
   Set-transformer architecture handles variable entity counts.

3. **PPO training loop** with action masking (~2 hours).

4. **Self-play league** (overnight + multiple days). Keep checkpoints of
   past versions; sample opponents from the league.

Expected lift: this is the long-game. The Lux AI S1 winner used PPO and
"seemed to be improving monotonically." A trained model SHOULD beat scripted
agents given enough training time. But "enough" might be 10-50K self-play
games — on CPU, that's days to weeks.

## Recommended sequencing

**Next session: Path A (real MCTS).** Highest near-term EV. Doesn't need
training infrastructure. Concrete deliverable.

**Session after that: Path B (behavior cloning).** Lower-risk than full RL.
Bootstraps a learned policy from real winning behavior.

**In parallel (background): Path C foundation.** Set up the training loop
and let it run between sessions. Even slow training accumulates over days.

## What we'd NEED to install / access

* `pip install torch` (CPU-only is OK; ~2GB)
* Kaggle API credentials (already on user's side)
* Bandwidth for replay downloads (~100 MB for 500 episodes)
* No GPU strictly required, but CPU training will limit us to small nets

## Open question for next session

Should I just rebuild a clean simulator + MCTS shell first (1 session), or
go straight to behavior cloning (which needs replay data first)? I lean
toward MCTS shell — it's a strict improvement on v28 and gives us a
**framework** that BC and RL can plug into later as the rollout evaluator.
