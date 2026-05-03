# Where we are after v28

## Validated standings (n=24 vs v14.8)

| Agent | Winrate | 95% CI | Catastrophic losses | Status |
|-------|---------|--------|---------------------|--------|
| v14.8 | (baseline) | — | — | Currently submitted, 878 ELO |
| v20c (phased PDR + HTVM=2.30) | **62.5%** | [43-79] | 3/24 | Validated |
| v23 (doctrine: no tiny probes) | — (untested at n=24 vs v14) | — | — | Doctrine fix |
| v27 (constraint aim, strict) | 41.7% | [22-64] | many | **Worse — don't ship** |
| **v28 (constraint + relaxation + reservation)** | **62.5%** | [43-79] | 5/24 | **Tied for best** |

**v28 and v20c are tied at 62.5% point estimate.** Both have wide CIs (lower bound ~43%). 

**Recommendation: ship v28**, not v20c, because:
1. v28 has the structural improvements (constraint aim, relaxation, target reservation) that should be more robust against the broader matchmaker pool than against just v14.8
2. Both have the same risk-of-no-improvement (CI lower bound below 50%)
3. v28's losses are concentrated in volume mismatches (v14.8 sometimes out-fires v28 5×) which is fixable in v29; v20c's failure modes are less clear

## What the README revealed (which we hadn't fully used)

I re-read the README carefully. Several mechanics matter more than we've been treating them:

### 1. **Combat math: same-owner fleets stack, top vs second-largest survives**

```
All arriving fleets are grouped by owner. 
The largest attacking force fights the second largest. 
The difference in ships survives.
```

In 4P, this matters a lot. If 3 players each send fleets to the same neutral, only the difference between top-1 and top-2 attackers actually engages the garrison. Sending 50 ships when top attacker has 60 means **your 50 are completely destroyed and your enemy gets paid 10 ships of damage.**

**v28 implication**: target reservation only checks ratio to defender. It should ALSO check incoming-from-other-players where possible. (We can't know enemy launches in advance, but we can see enemy fleets in flight.)

### 2. **Sweep: orbiting planets capture fleets in their arc**

```
Any fleet caught by a moving planet/comet is swept into combat with it.
```

This is mechanically important:
- Some "OOB" fleets in our diagnostic might actually be sweep-captures we missed
- Offensive opportunity: **park a fleet in an enemy orbiter's sweep path** — the planet sweeps INTO your fleet, free combat with no travel cost
- Defensive risk: enemy fleets passing near your orbiters get swept, helping you, but our fleets passing near enemy orbiters get captured

We have NEVER instrumented sweep-captures. The OOB diagnostic doesn't distinguish "left the board" from "hit a moving planet I didn't see coming."

### 3. **Comets spawn at fixed steps: 50, 150, 250, 350, 450**

Five waves. Each wave is 4 comets, one per quadrant, with production 1 and small radius.

**Currently the agent has no comet-anticipation logic.** v14.8 reacts to comets after they appear. A pre-comet move would:
- At step 49, identify the strongest planet near each quadrant's expected comet spawn point
- Pre-fleet a moderate force to arrive shortly after spawn
- Capture before any opponent gets there

This is a structural hack with potentially big returns — comet capture is "free production" for the rest of the game.

### 4. **Fleet speed nonlinearity is sharper than I treated it**

Recomputing the table from the README:
- 1 ship: 1.0/turn
- 20 ships: 2.4/turn
- 100 ships: 4.5/turn
- 500 ships: 5.0/turn
- 1000 ships: 6.0/turn

The "knee" is around 100-500 ships. Below 100, fleet speed grows fast with size. Above 500, it plateaus.

**Implication**: 50 + 50 (two fleets) is strictly worse than 100 + 0 in two ways:
- Combat math: two equal fleets arriving same turn produce 0 survivors (tie) — disaster
- Speed: two 50-ship fleets each move at 3.5/turn; one 100-ship moves at 4.5/turn

This validates your top-player observation about big chunky fleets even more strongly than the doctrine fix in v23 captured.

### 5. **Combat ties annihilate**

If two attackers tie on ship count, **both are destroyed completely**. Important in 4P scenarios. Our agent doesn't currently check whether an enemy fleet of the same size is heading to the same target.

## v29 plan (priority order)

### v29-A: Comet anticipation (structural, biggest expected gain)

At step 49 (and 149, 249, 349, 449), the agent computes a "comet pre-strike plan":
- Comets spawn at known patterns (4-fold symmetry, predictable orbits)
- For each quadrant, identify the closest player-owned planet to where comets will be
- Pre-launch fleets sized to capture comet starting garrisons (which are skewed-low: minimum of 4 rolls of 1-99, so usually 1-30 ships)

Implementation: 100-150 lines, special-case logic in `agent()` triggered at the right steps.

### v29-B: Sweep instrumentation + offensive sweep parking

Step 1: instrument the OOB diagnostic to distinguish "really OOB" from "captured by moving planet." This will tell us how big the sweep-loss problem really is.

Step 2: if sweep captures are common, add defensive sweep avoidance. If not, skip step 2.

Step 3 (offensive): when an enemy orbiter has high ship count and is rotating toward an empty sector of the board, send a fleet to a position the orbiter will sweep through. The orbiter then attacks itself into your fleet.

### v29-C: Better combat awareness in `is_target_saturated`

Currently checks: `incoming_friendly >= 2 × defender`. Should also check:
- If there's an enemy fleet in flight toward the same target with ships > our incoming, our attack will lose to combat math (top vs second). Skip.
- If our incoming + new attacker would tie with an inbound enemy, both annihilate. Skip.

This requires tracking enemy fleets' predicted arrivals (we have the math from v28's `v28_first_planet_hit`).

### v29-D: Fleet size threshold (the chunkiness lever)

Push `PARTIAL_SOURCE_MIN_SHIPS` higher than v23's 16 — try 25, 35. The README's speed curve suggests 50+ ship fleets are dramatically faster than 20-ship fleets. We may be under-shooting on this.

But this is a tuning change with high noise sensitivity; should be tested AFTER v29-A and v29-B since those are structural improvements.

## My recommendation

**Ship v28 today.** Then build v29-A first (comet anticipation) since it's the biggest structural gap and has the clearest implementation path.

Don't keep stacking complexity on v28 without testing each addition. The pattern from previous sessions has been: improvements measured in single-game look bigger than they are at n=24, and then the n=24 numbers have wide CIs. **Ship the validated improvement, then iterate.**
