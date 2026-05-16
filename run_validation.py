"""Local head-to-head validation harness."""
import argparse
import importlib.util
import math
import random
import sys
import time
import traceback
from kaggle_environments import make


def load_agent(path, suffix=""):
    name = f"agent_{suffix}_{random.random()}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def final_scores(state):
    obs = state[-1][0].observation
    n = len(state[-1])
    scores = [0] * n
    for p in obs.get("planets", []):
        if p[1] != -1:
            scores[p[1]] += p[5]
    for f in obs.get("fleets", []):
        scores[f[1]] += f[6]
    return scores


def wilson_ci(wins, total, z=1.96):
    if total == 0:
        return 0.0, 100.0
    p = wins / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return max(0, (centre - margin)) * 100, min(1, (centre + margin)) * 100


def h2h(challenger_path, baseline_path, n_games, steps, label, seed_base=42, act_timeout=10):
    print(f"\n=== {label}: {n_games} games × {steps} steps ===", flush=True)
    ch_w = bl_w = ties = 0
    log = []
    for g in range(n_games):
        random.seed(seed_base + g)
        env = make(
            "orbit_wars",
            configuration={"episodeSteps": steps, "actTimeout": act_timeout, "seed": seed_base + g},
            debug=False,
        )
        A = load_agent(challenger_path, f"ch_{g}")
        B = load_agent(baseline_path, f"bl_{g}")
        # Alternate seats
        if g % 2 == 0:
            agents = [A, B]
            ch_seat = 0
        else:
            agents = [B, A]
            ch_seat = 1
        t0 = time.time()
        try:
            state = env.run(agents)
        except Exception as exc:
            print(f"  g{g+1:2d}: ERROR {exc}", flush=True)
            traceback.print_exc()
            continue
        dt = time.time() - t0
        rewards = [s.reward for s in state[-1]]
        scores = final_scores(state)
        if rewards[0] == rewards[1]:
            ties += 1
            tag = "TIE"
        elif rewards[ch_seat] > rewards[1 - ch_seat]:
            ch_w += 1
            tag = "ch W"
        else:
            bl_w += 1
            tag = "bl W"
        log.append({"g": g + 1, "ch_seat": ch_seat, "result": tag, "scores": scores, "time_s": dt})
        print(
            f"  g{g+1:2d}: {tag:5s}  scores={scores}  seat={ch_seat}  t={dt:.1f}s",
            flush=True,
        )

    decisive = ch_w + bl_w
    wr = ch_w / decisive * 100 if decisive else 50.0
    lo, hi = wilson_ci(ch_w, decisive)
    print(
        f"\n  RESULT: {ch_w}W/{bl_w}L/{ties}T  winrate {wr:.1f}%  CI95 [{lo:.0f}–{hi:.0f}]",
        flush=True,
    )
    return {"wins": ch_w, "losses": bl_w, "ties": ties, "wr": wr, "ci": (lo, hi), "log": log}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ch", default="main.py", help="challenger agent path")
    parser.add_argument("--bl", default="v26.py", help="baseline agent path")
    parser.add_argument("-n", type=int, default=8)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--label", default="ch_vs_bl")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--act-timeout", type=int, default=10)
    args = parser.parse_args()

    h2h(
        args.ch,
        args.bl,
        args.n,
        args.steps,
        args.label,
        seed_base=args.seed,
        act_timeout=args.act_timeout,
    )
