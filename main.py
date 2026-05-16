"""Orbit Wars agent — clean rewrite (v30).

Design:
  * Exact target-position math (no fixed-point iteration / no off-board guesses).
  * Linear-search aim solver: smallest arrival turn T where speed(ships)*T covers
    the distance to target_pos_at(step+T), with sun avoidance.
  * Per-planet timeline simulation -> defense reservation + capture-cost.
  * Combat-aware: top-vs-second engagement; production-by-arrival included.
  * Distance-scaled chunky fleets (the speed curve rewards stacking).
  * Comet greedy: visible comets are top-priority capture targets.
"""

import math
import time
from collections import defaultdict, namedtuple

# ---------------------------------------------------------------------------
# Constants (must match engine — see kaggle_environments/envs/orbit_wars)
# ---------------------------------------------------------------------------

BOARD = 100.0
CENTER = 50.0
SUN_R = 10.0
SUN_SAFETY = 1.5             # extra clearance beyond SUN_R for aim safety
ROTATION_LIMIT = 50.0
MAX_SPEED = 6.0
TOTAL_STEPS = 500
LAUNCH_CLEARANCE = 0.1
COMET_SPAWN_STEPS = (50, 150, 250, 350, 450)
AIM_HORIZON = 120            # max turns to search for an aim

Planet = namedtuple("Planet", ["id", "owner", "x", "y", "radius", "ships", "production"])
Fleet = namedtuple("Fleet", ["id", "owner", "x", "y", "angle", "from_planet_id", "ships"])

# Persistent step counter (engine doesn't always expose obs.step)
_AGENT_STEP = 0

# ---------------------------------------------------------------------------
# Physics helpers
# ---------------------------------------------------------------------------

def fleet_speed(ships):
    if ships <= 1:
        return 1.0
    r = min(1.0, max(0.0, math.log(ships) / math.log(1000.0)))
    return 1.0 + (MAX_SPEED - 1.0) * (r ** 1.5)


def _seg_to_point(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    l2 = vx * vx + vy * vy
    if l2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * vx + (py - ay) * vy) / l2
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def sun_blocked(ax, ay, bx, by, safety=SUN_SAFETY):
    return _seg_to_point(CENTER, CENTER, ax, ay, bx, by) < SUN_R + safety


def _swept_pair_hit(ax, ay, bx, by, p0x, p0y, p1x, p1y, r):
    """Engine-equivalent: do fleet segment (A->B) and planet segment (P0->P1)
    come within `r` of each other for some t in [0, 1]?"""
    d0x, d0y = ax - p0x, ay - p0y
    dvx = (bx - ax) - (p1x - p0x)
    dvy = (by - ay) - (p1y - p0y)
    a = dvx * dvx + dvy * dvy
    b = 2.0 * (d0x * dvx + d0y * dvy)
    c = d0x * d0x + d0y * d0y - r * r
    if a < 1e-12:
        return c <= 0.0
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return False
    sq = math.sqrt(disc)
    t1 = (-b - sq) / (2.0 * a)
    t2 = (-b + sq) / (2.0 * a)
    return t2 >= 0.0 and t1 <= 1.0


def is_static_orbit(init_x, init_y, radius):
    r = math.hypot(init_x - CENTER, init_y - CENTER)
    return r + radius >= ROTATION_LIMIT


# ---------------------------------------------------------------------------
# World model
# ---------------------------------------------------------------------------

class World:
    """Snapshot of the game state with cached predictions and ETA helpers."""

    def __init__(self, obs, step):
        self.player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
        self.step = step
        self.remaining = max(1, TOTAL_STEPS - step)
        self.ang_vel = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
        self.comet_ids = set(obs.get("comet_planet_ids", []) if isinstance(obs, dict) else getattr(obs, "comet_planet_ids", []))
        self.comets = obs.get("comets", []) if isinstance(obs, dict) else getattr(obs, "comets", [])

        raw_planets = obs.get("planets", []) if isinstance(obs, dict) else getattr(obs, "planets", [])
        raw_fleets = obs.get("fleets", []) if isinstance(obs, dict) else getattr(obs, "fleets", [])
        raw_init = obs.get("initial_planets", []) if isinstance(obs, dict) else getattr(obs, "initial_planets", [])

        self.planets = [Planet(*p) for p in raw_planets]
        self.fleets = [Fleet(*f) for f in raw_fleets]
        self.planet_by_id = {p.id: p for p in self.planets}

        # Initial orbit params (id -> (theta0, r, is_static))
        self._orbit = {}
        for p in raw_init:
            pid, _, ix, iy, rad, _, _ = p
            r = math.hypot(ix - CENTER, iy - CENTER)
            static = r + rad >= ROTATION_LIMIT
            theta0 = math.atan2(iy - CENTER, ix - CENTER)
            self._orbit[pid] = (theta0, r, static)

        # Comet path lookup
        self._comet_path = {}
        for group in self.comets:
            pids = group.get("planet_ids", [])
            paths = group.get("paths", [])
            idx = group.get("path_index", 0)
            for i, pid in enumerate(pids):
                if i < len(paths):
                    self._comet_path[pid] = (paths[i], idx)

        # Groupings
        self.my_planets = [p for p in self.planets if p.owner == self.player]
        self.enemy_planets = [p for p in self.planets if p.owner not in (-1, self.player)]
        self.neutral_planets = [p for p in self.planets if p.owner == -1]

        # Player stats
        self.owner_strength = defaultdict(int)
        self.owner_production = defaultdict(int)
        for p in self.planets:
            if p.owner != -1:
                self.owner_strength[p.owner] += int(p.ships)
                self.owner_production[p.owner] += int(p.production)
        for f in self.fleets:
            self.owner_strength[f.owner] += int(f.ships)
        self.num_players = max(2, len({o for o in self.owner_strength if o >= 0}))
        self.is_4p = self.num_players >= 4

        # Aim cache
        self._aim_cache = {}

    # -- target position prediction --

    def target_pos_at(self, target_id, future_t):
        """Return (x, y) of target at current_step + future_t. None if comet expired."""
        if target_id in self._comet_path:
            path, idx = self._comet_path[target_id]
            i = idx + int(future_t)
            if 0 <= i < len(path):
                return path[i][0], path[i][1]
            return None
        orbit = self._orbit.get(target_id)
        if orbit is None:
            p = self.planet_by_id.get(target_id)
            return (p.x, p.y) if p else None
        theta0, r, static = orbit
        if static:
            p = self.planet_by_id[target_id]
            return (p.x, p.y)
        # engine: current_angle = theta0 + ang_vel * step  (where step advances each tick).
        # So position after `future_t` ticks from now:
        ang = theta0 + self.ang_vel * (self.step + future_t)
        return (CENTER + r * math.cos(ang), CENTER + r * math.sin(ang))

    def comet_life_left(self, target_id):
        if target_id not in self._comet_path:
            return 10**9
        path, idx = self._comet_path[target_id]
        return max(0, len(path) - idx)

    # -- aim solver --

    def aim(self, src, target_id, ships):
        """Smallest arrival turn T (>=1) and launch angle for fleet of `ships`.
        Returns (angle, T, (tx, ty)) or None.

        Verifies the result via swept-pair geometry (matches engine collision
        detection) and refuses paths that leave the board or cross the sun.
        """
        key = (src.id, target_id, int(ships))
        if key in self._aim_cache:
            return self._aim_cache[key]
        speed = fleet_speed(ships)
        sx, sy, sr = src.x, src.y, src.radius
        max_t = min(AIM_HORIZON, self.remaining - 1)
        if target_id in self._comet_path:
            max_t = min(max_t, self.comet_life_left(target_id) - 1)
        if max_t < 1:
            self._aim_cache[key] = None
            return None
        tgt_p = self.planet_by_id.get(target_id)
        if tgt_p is None:
            self._aim_cache[key] = None
            return None
        tgt_r = tgt_p.radius
        result = None
        for T in range(1, max_t + 1):
            pos = self.target_pos_at(target_id, T)
            if pos is None:
                continue
            tx, ty = pos
            # Aim straight at predicted end-of-turn position
            angle = math.atan2(ty - sy, tx - sx)
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            launch_x = sx + cos_a * (sr + LAUNCH_CLEARANCE)
            launch_y = sy + sin_a * (sr + LAUNCH_CLEARANCE)
            # Fleet positions at start and end of turn T (from launch_pt origin)
            fleet_T_start_x = launch_x + cos_a * (T - 1) * speed
            fleet_T_start_y = launch_y + sin_a * (T - 1) * speed
            fleet_T_end_x = launch_x + cos_a * T * speed
            fleet_T_end_y = launch_y + sin_a * T * speed
            # Reject if path leaves the board
            if not (0 <= fleet_T_end_x <= BOARD and 0 <= fleet_T_end_y <= BOARD):
                continue
            # Reject if path crosses sun (anywhere along [launch, end_of_T])
            if sun_blocked(launch_x, launch_y, fleet_T_end_x, fleet_T_end_y):
                continue
            # Target positions at start and end of turn T (engine sweeps planet from
            # angle@(step+T-1) to angle@(step+T) during turn step+T).
            prev_pos = self.target_pos_at(target_id, T - 1) if T >= 1 else (tgt_p.x, tgt_p.y)
            if prev_pos is None:
                continue
            ptx, pty = prev_pos
            # Verify swept-pair hit during turn T (matches engine math).
            if _swept_pair_hit(
                fleet_T_start_x, fleet_T_start_y, fleet_T_end_x, fleet_T_end_y,
                ptx, pty, tx, ty, tgt_r,
            ):
                result = (angle, T, (tx, ty))
                break
        self._aim_cache[key] = result
        return result

# ---------------------------------------------------------------------------
# Arrival ledger & timeline simulation
# ---------------------------------------------------------------------------

def fleet_planet_eta(fleet, world):
    """Estimate which planet (if any) a fleet will collide with, and when.
    Continuous-collision approximation: closest planet whose perp distance to the
    fleet's ray is < planet.radius. Returns (planet_id, eta) or (None, None).
    """
    dirx, diry = math.cos(fleet.angle), math.sin(fleet.angle)
    speed = fleet_speed(fleet.ships)
    best = (None, None)
    best_t = 10**9
    for p in world.planets:
        # Predict planet positions along a few candidate ETAs; for simplicity
        # use current planet position (good enough for static; orbiters move
        # slowly relative to fleet so close-enough).
        dx = p.x - fleet.x
        dy = p.y - fleet.y
        proj = dx * dirx + dy * diry
        if proj < 0:
            continue
        perp_sq = dx * dx + dy * dy - proj * proj
        rad_sq = p.radius * p.radius
        if perp_sq >= rad_sq:
            continue
        hit_d = max(0.0, proj - math.sqrt(max(0.0, rad_sq - perp_sq)))
        t = hit_d / speed if speed > 0 else 10**9
        if t < best_t:
            best_t = t
            best = (p.id, int(math.ceil(t)) or 1)
    return best


def build_arrivals(world):
    """For each planet, list of (eta, owner, ships) for fleets currently in flight."""
    arrivals = defaultdict(list)
    for f in world.fleets:
        pid, eta = fleet_planet_eta(f, world)
        if pid is None:
            continue
        arrivals[pid].append((eta, f.owner, int(f.ships)))
    return arrivals


def simulate_planet(planet, arrivals, player, horizon):
    """Simulate a planet over `horizon` turns given incoming arrivals.
    Returns dict with:
      owner_at[t], ships_at[t], keep_needed, fall_turn (first turn player loses
      it; None if holds), holds, min_owned_ships.
    Combat math mirrors the engine: top vs second, ties annihilate, leftover
    fights garrison.
    """
    by_turn = defaultdict(list)
    for eta, owner, ships in arrivals:
        if eta <= horizon and ships > 0:
            by_turn[max(1, int(eta))].append((owner, ships))

    owner = planet.owner
    garrison = float(planet.ships)
    owner_at = {0: owner}
    ships_at = {0: garrison}
    fall_turn = None
    holds = owner == player
    min_owned = garrison if owner == player else 0.0

    for t in range(1, horizon + 1):
        if owner != -1:
            garrison += planet.production
        events = by_turn.get(t)
        if events:
            per_owner = defaultdict(int)
            for o, s in events:
                per_owner[o] += s
            sorted_p = sorted(per_owner.items(), key=lambda kv: -kv[1])
            top_o, top_s = sorted_p[0]
            if len(sorted_p) > 1 and sorted_p[1][1] == top_s:
                # tie -> all annihilate
                surv_o, surv_s = -1, 0
            elif len(sorted_p) > 1:
                surv_o, surv_s = top_o, top_s - sorted_p[1][1]
            else:
                surv_o, surv_s = top_o, top_s
            if surv_s > 0:
                if owner == surv_o:
                    garrison += surv_s
                else:
                    garrison -= surv_s
                    if garrison < 0:
                        prev_owner = owner
                        owner = surv_o
                        garrison = -garrison
                        if prev_owner == player and owner != player and fall_turn is None:
                            fall_turn = t
                            holds = False
        owner_at[t] = owner
        ships_at[t] = max(0.0, garrison)
        if owner == player:
            min_owned = min(min_owned, garrison)

    # Keep-needed: binary search smallest garrison such that planet holds for the
    # whole horizon, assuming current arrivals.
    keep_needed = 0
    if planet.owner == player:
        def holds_with(k):
            g = float(k)
            o = planet.owner
            for t in range(1, horizon + 1):
                if o != -1:
                    g += planet.production
                events = by_turn.get(t)
                if events:
                    per_owner = defaultdict(int)
                    for ow, s in events:
                        per_owner[ow] += s
                    sp = sorted(per_owner.items(), key=lambda kv: -kv[1])
                    to, ts = sp[0]
                    if len(sp) > 1 and sp[1][1] == ts:
                        ss = 0
                        so = -1
                    elif len(sp) > 1:
                        so, ss = to, ts - sp[1][1]
                    else:
                        so, ss = to, ts
                    if ss > 0:
                        if o == so:
                            g += ss
                        else:
                            g -= ss
                            if g < 0:
                                return False
            return True
        lo, hi = 0, int(planet.ships) + 1
        if holds_with(hi):
            while lo < hi:
                mid = (lo + hi) // 2
                if holds_with(mid):
                    hi = mid
                else:
                    lo = mid + 1
            keep_needed = lo
        else:
            keep_needed = int(planet.ships)
            holds = False

    return {
        "owner_at": owner_at,
        "ships_at": ships_at,
        "keep_needed": keep_needed,
        "fall_turn": fall_turn,
        "holds": holds,
        "min_owned": int(max(0, math.floor(min_owned))),
    }


def owner_at_turn(planet, arrivals, horizon):
    """Fast version of simulate_planet that only computes (owner, ships) at the
    end of `horizon`. No keep_needed binary search."""
    by_turn = defaultdict(list)
    for eta, owner, ships in arrivals:
        eta = max(1, int(math.ceil(eta)))
        if eta <= horizon and ships > 0:
            by_turn[eta].append((owner, ships))
    owner = planet.owner
    garrison = float(planet.ships)
    for t in range(1, horizon + 1):
        if owner != -1:
            garrison += planet.production
        events = by_turn.get(t)
        if not events:
            continue
        per_owner = defaultdict(int)
        for o, s in events:
            per_owner[o] += s
        sorted_p = sorted(per_owner.items(), key=lambda kv: -kv[1])
        top_o, top_s = sorted_p[0]
        if len(sorted_p) > 1 and sorted_p[1][1] == top_s:
            surv_o, surv_s = -1, 0
        elif len(sorted_p) > 1:
            surv_o, surv_s = top_o, top_s - sorted_p[1][1]
        else:
            surv_o, surv_s = top_o, top_s
        if surv_s > 0:
            if owner == surv_o:
                garrison += surv_s
            else:
                garrison -= surv_s
                if garrison < 0:
                    owner = surv_o
                    garrison = -garrison
    return owner, max(0.0, garrison)


def projected_state_at(planet, arrivals, player, t):
    """Owner & ships at end of turn t given arrivals (alias for owner_at_turn)."""
    return owner_at_turn(planet, arrivals, t)


def capture_cost(target, arrivals, player, arrival_turn):
    """Minimum ships our fleet must arrive with to OWN the target after combat
    at `arrival_turn`. Accounts for enemy/friendly fleets en route + production.
    Binary search via simulating extra arrival.
    """
    base_arrivals = list(arrivals)
    def owns_with(k):
        sim = base_arrivals + [(arrival_turn, player, int(k))]
        owner, _ = projected_state_at(target, sim, player, arrival_turn)
        return owner == player
    # Quick upper bound
    cap = max(50, int(target.ships) + target.production * arrival_turn + 200)
    if not owns_with(cap):
        return cap + 1
    lo, hi = 1, cap
    while lo < hi:
        mid = (lo + hi) // 2
        if owns_with(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

def min_send_for_distance(d):
    """Distance-scaled minimum fleet size — speed curve rewards stacking."""
    if d <= 15:
        return 15
    if d <= 30:
        return 22
    if d <= 50:
        return 32
    if d <= 70:
        return 48
    return 60


def target_value(target, world, arrival_turn):
    """Long-term value of owning `target` from arrival_turn onward."""
    life = world.remaining - arrival_turn
    if life <= 0:
        return 0.0
    is_comet = target.id in world.comet_ids
    if is_comet:
        life = min(life, world.comet_life_left(target.id) - arrival_turn)
        if life <= 0:
            return 0.0
    value = target.production * life
    # Static planets are more durable -> higher value
    orbit = world._orbit.get(target.id)
    if orbit and orbit[2]:
        value *= 1.25
    # Enemy planets worth more (capturing removes their production)
    if target.owner not in (-1, world.player):
        value *= 1.8
        weakest = _weakest_enemy(world)
        if weakest is not None and target.owner == weakest:
            value *= 1.35 if world.is_4p else 1.2
    # Comets: short-lived but cheap to grab; denial value is real.
    if is_comet:
        # 1 production for `life` turns + denial bonus (the opponent would have
        # gotten it otherwise). Add a flat bonus so they out-score boring far
        # neutrals when nearby.
        value += 25
    return value


def _weakest_enemy(world):
    candidates = [o for o, _ in world.owner_strength.items() if o not in (-1, world.player)]
    if not candidates:
        return None
    return min(candidates, key=lambda o: world.owner_strength[o] + 15 * world.owner_production.get(o, 0))


def plan_moves(world, deadline):
    arrivals = build_arrivals(world)

    # 1. Per-my-planet defense reservation
    horizon = 40
    reserve = {}
    timelines = {}
    for p in world.my_planets:
        tl = simulate_planet(p, arrivals.get(p.id, []), world.player, horizon)
        timelines[p.id] = tl
        # Proactive: nearest enemy planet within ~15-turn strike range; reserve a fraction.
        proactive = 0
        for ep in world.enemy_planets:
            d = math.hypot(p.x - ep.x, p.y - ep.y)
            if d > 60:
                continue
            est_eta = d / fleet_speed(max(1, int(ep.ships)))
            if est_eta > 18:
                continue
            proactive = max(proactive, int(ep.ships * 0.30))
        baseline = max(2, int(p.production * 2))
        reserve[p.id] = min(int(p.ships), max(tl["keep_needed"], proactive, baseline))

    # Available attack budget per source
    budget = {p.id: max(0, int(p.ships) - reserve[p.id]) for p in world.my_planets}
    # Track ships committed this turn
    spent = defaultdict(int)
    planned_arrivals = defaultdict(list)  # additional fleets we will send

    def src_left(src_id):
        return max(0, budget[src_id] - spent[src_id])

    moves = []

    def append_move(src_id, angle, ships):
        n = min(int(ships), src_left(src_id))
        if n < 1:
            return 0
        moves.append([src_id, float(angle), int(n)])
        spent[src_id] += n
        return n

    # 2. Build candidate (src, target) scored options
    candidates = []
    for src in world.my_planets:
        if src_left(src.id) < 1:
            continue
        for target in world.planets:
            if target.id == src.id or target.owner == world.player:
                continue
            if time.perf_counter() > deadline:
                break
            cap = src_left(src.id)
            aim = world.aim(src, target.id, cap)
            if aim is None:
                continue
            angle, T, (tx, ty) = aim
            d = math.hypot(tx - src.x, ty - src.y)
            # combined arrivals = base + already-planned
            combined = arrivals.get(target.id, []) + planned_arrivals.get(target.id, [])
            need = capture_cost(target, combined, world.player, T)
            if need > cap:
                continue
            # Enforce minimum send for distance (but never above need + cap-buffer)
            min_send = min_send_for_distance(d)
            # Margin: small buffer for unforeseen reinforcements
            margin = 2 + int(target.production)
            if target.owner not in (-1, world.player):
                margin += 4
            send = max(need + margin, min_send)
            send = min(send, cap)
            if send < need:
                continue
            # Don't launch tiny fleets at distant targets — speed curve
            # destroys them and ties annihilate.
            if send < min_send and d > 18:
                continue
            if send < 5:
                continue
            value = target_value(target, world, T)
            if value <= 0:
                continue
            # Cost = ships sent + travel time penalty
            cost = send + 0.5 * T
            score = value / (cost + 1.0)
            # Comet boost (short window, must move fast)
            if target.id in world.comet_ids:
                score *= 1.15
            candidates.append((score, src.id, target.id, angle, T, send, need))
        if time.perf_counter() > deadline:
            break

    # 3. Greedy execution
    candidates.sort(key=lambda c: -c[0])
    used_targets = set()
    for score, src_id, target_id, angle, T, send, need in candidates:
        if time.perf_counter() > deadline:
            break
        if target_id in used_targets:
            continue
        left = src_left(src_id)
        if left < need:
            continue
        # re-check capture cost with updated planned arrivals
        target = world.planet_by_id[target_id]
        combined = arrivals.get(target.id, []) + planned_arrivals.get(target.id, [])
        recheck = capture_cost(target, combined, world.player, T)
        if recheck > left:
            continue
        send = max(min(left, send), recheck + 2)
        send = min(send, left)
        if send < recheck:
            continue
        # Re-aim with actual send count (speed may differ slightly)
        src = world.planet_by_id[src_id]
        aim2 = world.aim(src, target_id, send)
        if aim2 is None:
            continue
        angle, T, _ = aim2
        actual = append_move(src_id, angle, send)
        if actual >= recheck:
            planned_arrivals[target_id].append((T, world.player, actual))
            used_targets.add(target_id)

    # 4. Rescue: if any of my planets is doomed and a neighbor can save it
    for me in world.my_planets:
        tl = timelines[me.id]
        ft = tl["fall_turn"]
        if ft is None or ft > 30:
            continue
        if time.perf_counter() > deadline:
            break
        # how many ships need to arrive by ft to keep it
        for ally in world.my_planets:
            if ally.id == me.id:
                continue
            cap = src_left(ally.id)
            if cap < 8:
                continue
            aim = world.aim(ally, me.id, cap)
            if aim is None:
                continue
            angle, T, _ = aim
            if T > ft:
                continue
            # how many ships do we need from this ally?
            combined = arrivals.get(me.id, []) + planned_arrivals.get(me.id, [])
            def survives_with(k):
                sim = combined + [(T, world.player, int(k))]
                owner, _ = projected_state_at(me, sim, world.player, max(ft, T) + 2)
                return owner == world.player
            need = 0
            lo, hi = 0, cap
            if not survives_with(hi):
                continue
            while lo < hi:
                mid = (lo + hi) // 2
                if survives_with(mid):
                    hi = mid
                else:
                    lo = mid + 1
            need = lo
            if need <= 0 or need > cap:
                continue
            send = min(cap, need + 2)
            aim2 = world.aim(ally, me.id, send)
            if aim2 is None:
                continue
            angle, T, _ = aim2
            actual = append_move(ally.id, angle, send)
            if actual > 0:
                planned_arrivals[me.id].append((T, world.player, actual))
                break  # one rescuer per planet per turn

    return moves


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def agent(obs, config=None):
    start = time.perf_counter()
    obs_step = obs.get("step", 0) if isinstance(obs, dict) else getattr(obs, "step", 0)
    step = obs_step or 0
    world = World(obs, step)
    if not world.my_planets:
        return []
    act_timeout = 1.0
    if config is not None:
        act_timeout = config.get("actTimeout", 1.0) if isinstance(config, dict) else getattr(config, "actTimeout", 1.0)
    soft = min(0.85, max(0.55, act_timeout * 0.82))
    deadline = start + soft
    return plan_moves(world, deadline)


__all__ = ["agent"]
