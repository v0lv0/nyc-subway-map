"""Build a schematic (octolinear) layout of the subway network from map_data.json.

Output static/schematic.json:
  { nodes: {id: [x,y]}, routes: {routeId: [orderedStopIds]},
    colors: {...}, names: {id: name} }

The frontend rebuilds each route's polyline by connecting its stations' schematic
positions in order, so live trains still interpolate by arc-length along the line.
"""
import json
import math
from collections import defaultdict

d = json.load(open("static/map_data.json"))
stops = {s["id"]: s for s in d["stops"]}

# --- Network from route_paths (each route's stations in track order) ----------
routes = {}          # routeId -> [orderedStopIds]
edges = {}           # (a,b) sorted -> set(routeIds)
for rid, rp in d["route_paths"].items():
    seq = [sid for sid, _ in sorted(rp["stopT"].items(), key=lambda kv: kv[1])
           if sid in stops]
    # drop consecutive duplicates
    seq = [s for i, s in enumerate(seq) if i == 0 or s != seq[i - 1]]
    if len(seq) < 2:
        continue
    routes[rid] = seq
    for a, b in zip(seq, seq[1:]):
        edges.setdefault(tuple(sorted((a, b))), set()).add(rid)

nodes = sorted({n for e in edges for n in e})


def _geolen(e):
    a, b = e
    return math.hypot(stops[a]["lat"] - stops[b]["lat"],
                      stops[a]["lon"] - stops[b]["lon"])


# Edges used to CONSTRAIN the layout: drop express "skip" edges (much longer than
# a normal hop) so the trunk lays out as one clean local chain. Express lines are
# still drawn (from `routes`); they just don't distort the solver.
_lens = sorted(_geolen(e) for e in edges)
_median = _lens[len(_lens) // 2] or 1e-9
solver_edges = [e for e in edges if _geolen(e) <= 2.2 * _median]

# --- Initial positions: geographic, rotated so Manhattan stands ~vertical -----
clat = sum(stops[n]["lat"] for n in nodes) / len(nodes)
clon = sum(stops[n]["lon"] for n in nodes) / len(nodes)
coslat = math.cos(clat * math.pi / 180)
SCALE = 3000.0
ROT = 29 * math.pi / 180
_cT, _sT = math.cos(ROT), math.sin(ROT)


def _xy(lat, lon):
    ex, ny = (lon - clon) * coslat, (lat - clat)
    return [(ex * _cT - ny * _sT) * SCALE, (ex * _sT + ny * _cT) * SCALE]


pos = {n: _xy(stops[n]["lat"], stops[n]["lon"]) for n in nodes}
orig = {n: list(p) for n, p in pos.items()}

# --- Pin Manhattan trunk lines into ordered vertical columns ------------------
# This gives the solver the "line ordering" it can't infer: the north-south
# avenues, west->east. Stations keep their (rotated) latitude as y, so vertical
# order is preserved; x is snapped to the avenue's column.
station_routes = defaultdict(set)
for rid, seq in routes.items():
    for s in seq:
        station_routes[s].add(rid)

AVENUES = [                       # (routes, column index west->east)
    (["A", "C", "E"], -2.0),      # 8th Av
    (["1", "2", "3"], -1.0),      # 7th Av
    (["B", "D", "F", "M"], 0.0),  # 6th Av
    (["N", "Q", "R", "W"], 1.0),  # Broadway
    (["4", "5", "6"], 2.0),       # Lexington Av
]
COL = 42.0  # horizontal spacing between avenue columns


def _in_manhattan(n):
    la, lo = stops[n]["lat"], stops[n]["lon"]
    return 40.70 <= la <= 40.88 and -74.03 <= lo <= -73.93


_mxs = [pos[n][0] for n in nodes if _in_manhattan(n)]
_mcx = sum(_mxs) / len(_mxs) if _mxs else 0.0

pinned = {}
for n in nodes:
    if not _in_manhattan(n):
        continue
    best, best_ov = None, 0
    for rlist, col in AVENUES:
        ov = len(station_routes[n] & set(rlist))
        if ov > best_ov:
            best, best_ov = col, ov
    if best is not None:
        pinned[n] = [_mcx + best * COL, orig[n][1]]
for n, p in pinned.items():
    pos[n] = list(p)

# --- Octolinear layout: fixed directions + least-squares (Gauss-Seidel) -------
# Each edge's direction is snapped ONCE to the nearest 45-deg from geography and
# held fixed; we then solve for node positions that best satisfy those directions
# at a target length. This converges to clean, straight lines (unlike re-snapping
# every iteration, which oscillates).
ITERS = 220
ANCHOR = 0.05    # weak pull to true geography (keeps shape/orientation)
MIN_EDGE = 18.0  # target edge length -> even spacing, spreads dense areas
SEP = 17.0       # min separation; light repulsion without hurting octolinearity
REP = 0.5        # repulsion strength
OCT = math.pi / 4

# Per edge, fixed target vector a->b (octolinear direction * length).
nbr = defaultdict(list)
for (a, b) in solver_edges:
    dx, dy = orig[b][0] - orig[a][0], orig[b][1] - orig[a][1]
    ang = round(math.atan2(dy, dx) / OCT) * OCT
    L = max(math.hypot(dx, dy), MIN_EDGE)
    vx, vy = math.cos(ang) * L, math.sin(ang) * L
    nbr[a].append((b, -vx, -vy))   # target for a = pos[b] - v
    nbr[b].append((a, vx, vy))     # target for b = pos[a] + v

for _ in range(ITERS):
    # 1) satisfy octolinear edge directions (Gauss-Seidel); pinned nodes are fixed
    for n in nodes:
        if n in pinned:
            continue
        sx, sy, c = ANCHOR * orig[n][0], ANCHOR * orig[n][1], ANCHOR
        for (m, ox, oy) in nbr[n]:
            sx += pos[m][0] + ox
            sy += pos[m][1] + oy
            c += 1
        pos[n][0] = sx / c
        pos[n][1] = sy / c
    # 2) push apart nearby stations (spatial grid for speed)
    grid = defaultdict(list)
    for n in nodes:
        grid[(int(pos[n][0] // SEP), int(pos[n][1] // SEP))].append(n)
    for n in nodes:
        if n in pinned:
            continue
        gx, gy = int(pos[n][0] // SEP), int(pos[n][1] // SEP)
        fx = fy = 0.0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for m in grid.get((gx + dx, gy + dy), ()):
                    if m == n:
                        continue
                    ddx = pos[n][0] - pos[m][0]
                    ddy = pos[n][1] - pos[m][1]
                    dist = math.hypot(ddx, ddy)
                    if 0 < dist < SEP:
                        push = (SEP - dist) / dist
                        fx += ddx * push
                        fy += ddy * push
        pos[n][0] += REP * fx
        pos[n][1] += REP * fy

# --- Measure octolinearity (how close edges are to 45-deg multiples) ----------
err = 0.0
for (a, b) in solver_edges:
    dx = pos[b][0] - pos[a][0]
    dy = pos[b][1] - pos[a][1]
    ang = math.atan2(dy, dx)
    err += abs(ang - round(ang / OCT) * OCT)
err /= len(solver_edges)

# Drawn path per route follows the physical local chain (so express lines don't
# cut straight across). `stops` stays the actual stop list (for train arc-length).
from collections import deque

adj = defaultdict(list)
for (a, b) in solver_edges:
    adj[a].append(b)
    adj[b].append(a)


def _bfs(a, b):
    if a == b:
        return [a]
    prev = {a: None}
    q = deque([a])
    while q:
        u = q.popleft()
        if u == b:
            break
        for w in adj[u]:
            if w not in prev:
                prev[w] = u
                q.append(w)
    if b not in prev:
        return [a, b]
    path, u = [], b
    while u is not None:
        path.append(u)
        u = prev[u]
    return path[::-1]


routes_out = {}
for rid, seq in routes.items():
    draw = [seq[0]]
    for a, b in zip(seq, seq[1:]):
        key = tuple(sorted((a, b)))
        if key in edges and _geolen(key) <= 2.2 * _median:
            draw.append(b)
        else:
            p = _bfs(a, b)
            draw.extend(p[1:] if p and p[0] == draw[-1] else p)
    routes_out[rid] = {"draw": draw, "stops": seq}

out = {
    "nodes": {n: [round(pos[n][0], 2), round(pos[n][1], 2)] for n in nodes},
    "routes": routes_out,
    "colors": d["route_colors"],
    "names": {n: stops[n]["name"] for n in nodes},
}
with open("static/schematic.json", "w") as f:
    json.dump(out, f)

print(f"nodes: {len(nodes)}  edges: {len(edges)}  solver_edges: {len(solver_edges)}  routes: {len(routes)}")
print(f"mean octolinear angle error: {math.degrees(err):.2f} deg (lower=straighter)")
print("Written static/schematic.json")
