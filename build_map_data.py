import csv
import json
from collections import defaultdict

# Staten Island routes to exclude
EXCLUDE_ROUTES = {"SI", "SIR"}


def is_staten_island(stop_id):
    # SIR stops are S09-S31. S01-S04 are the Franklin Ave Shuttle (Brooklyn) -- keep.
    return (
        stop_id.startswith("S")
        and stop_id[1:].isdigit()
        and int(stop_id[1:]) >= 9
    )


stops = {}
with open("data/stops.txt") as f:
    for row in csv.DictReader(f):
        # Keep only parent stations (location_type 1) -- one dot per station.
        # Platform stops (L17N/L17S) share coords and are matched at runtime by
        # stripping the N/S suffix back to the parent id.
        if row["location_type"] != "1":
            continue
        if is_staten_island(row["stop_id"]):
            continue
        stops[row["stop_id"]] = {
            "id": row["stop_id"],
            "name": row["stop_name"],
            "lat": round(float(row["stop_lat"]), 5),
            "lon": round(float(row["stop_lon"]), 5),
        }

raw_shapes = defaultdict(list)
with open("data/shapes.txt") as f:
    for row in csv.DictReader(f):
        raw_shapes[row["shape_id"]].append(
            (
                int(row["shape_pt_sequence"]),
                float(row["shape_pt_lat"]),
                float(row["shape_pt_lon"]),
            )
        )

shapes = {}
for sid, pts in raw_shapes.items():
    pts.sort(key=lambda x: x[0])
    shapes[sid] = [[round(p[1], 5), round(p[2], 5)] for p in pts]

route_colors = {}
with open("data/routes.txt") as f:
    for row in csv.DictReader(f):
        if row["route_id"] in EXCLUDE_ROUTES:
            continue
        color = row.get("route_color", "").strip() or "888888"
        route_colors[row["route_id"]] = "#" + color

route_shapes = defaultdict(set)
with open("data/trips.txt") as f:
    for row in csv.DictReader(f):
        rid = row["route_id"]
        if rid in EXCLUDE_ROUTES:
            continue
        sid = row["shape_id"]
        if sid:
            route_shapes[rid].add(sid)

route_shape_list = {}
for rid, sids in route_shapes.items():
    route_shape_list[rid] = [
        shapes[sid] for sid in sids if sid in shapes and len(shapes[sid]) > 10
    ]


def _path_len(pts):
    tot = 0.0
    for i in range(1, len(pts)):
        dy = pts[i][0] - pts[i - 1][0]
        dx = pts[i][1] - pts[i - 1][1]
        tot += (dy * dy + dx * dx) ** 0.5
    return tot


def _seg_intersect(a, b, c, d):
    """Intersection point of segments a-b and c-d, or None. Points are [lat,lon]."""
    # work in (x=lon, y=lat)
    ax, ay = a[1], a[0]
    bx, by = b[1], b[0]
    cx, cy = c[1], c[0]
    dx_, dy_ = d[1], d[0]
    rx, ry = bx - ax, by - ay
    sx, sy = dx_ - cx, dy_ - cy
    denom = rx * sy - ry * sx
    if denom == 0:
        return None  # parallel / collinear -- leave it
    t = ((cx - ax) * sy - (cy - ay) * sx) / denom
    u = ((cx - ax) * ry - (cy - ay) * rx) / denom
    if 0.0 < t < 1.0 and 0.0 < u < 1.0:
        return [round(ay + t * ry, 6), round(ax + t * rx, 6)]
    return None


def _deloop(path, radius=0.0009, window=120, min_span=3, detour=2.5):
    """Remove loops, hairpins, and out-and-back spurs baked into the GTFS track
    shape (e.g. the South Ferry balloon loop). Within a local `window` of
    vertices, find where the path returns within `radius` (~90m) of an earlier
    point AND the interior actually doubled back -- its arc-length is at least
    `detour`x the straight gap. That span is excised and the ends joined across.

    The detour guard is what makes it safe: a straight or gently-curving run has
    arc-length ~= its chord (ratio ~1) so it is never touched; only a genuine
    loop/spur (which travels far and returns near its start) clears the
    threshold. The straight chord across the small gap is invisible at city
    scale."""
    pts = [p[:] for p in path]
    i = 0
    while i < len(pts) - 1:
        hi = min(len(pts) - 1, i + window)
        # cumulative arc-length from i, so we can test the detour ratio cheaply
        arc = 0.0
        cut = None
        for j in range(i + 1, hi + 1):
            dy = pts[j][0] - pts[j - 1][0]
            dx = pts[j][1] - pts[j - 1][1]
            arc += (dy * dy + dx * dx) ** 0.5
            if j - i < min_span:
                continue
            gy = pts[j][0] - pts[i][0]
            gx = pts[j][1] - pts[i][1]
            gap = (gy * gy + gx * gx) ** 0.5
            if gap <= radius and arc >= detour * max(gap, 1e-9):
                cut = j  # keep scanning: take the farthest qualifying return
        if cut is not None:
            pts = pts[: i + 1] + pts[cut + 1 :]  # drop the loop/spur interior
        i += 1
    return pts


def _snap(lat, lon, pts, cum):
    """Nearest point on the polyline -> (distance, normalized arclength)."""
    best_d = float("inf")
    best_s = 0.0
    for i in range(1, len(pts)):
        ay, ax = pts[i - 1]
        by, bx = pts[i]
        dy, dx = by - ay, bx - ax
        seg2 = dy * dy + dx * dx
        if seg2 == 0:
            continue
        t = ((lat - ay) * dy + (lon - ax) * dx) / seg2
        t = max(0.0, min(1.0, t))
        py, px = ay + t * dy, ax + t * dx
        d = ((lat - py) ** 2 + (lon - px) ** 2) ** 0.5
        if d < best_d:
            best_d = d
            best_s = cum[i - 1] + t * (cum[i] - cum[i - 1])
    return best_d, best_s


# Per-route track geometry: representative (longest) shape + each nearby stop's
# normalized arclength along it. Lets the frontend glide trains along the curve.
SNAP_THRESH = 0.0018  # ~180m in degrees; stop must be this close to the trunk
route_paths = {}
for rid, shape_list in route_shape_list.items():
    if not shape_list:
        continue
    path = max(shape_list, key=_path_len)
    if len(path) < 2:
        continue
    path = _deloop(path)  # drop South-Ferry-style self-intersection knots
    cum = [0.0]
    for i in range(1, len(path)):
        dy = path[i][0] - path[i - 1][0]
        dx = path[i][1] - path[i - 1][1]
        cum.append(cum[-1] + (dy * dy + dx * dx) ** 0.5)
    total = cum[-1] or 1.0
    cum = [round(c / total, 6) for c in cum]
    stop_t = {}
    for st in stops.values():
        d, s = _snap(st["lat"], st["lon"], path, cum)
        if d <= SNAP_THRESH:
            stop_t[st["id"]] = round(s, 6)
    route_paths[rid] = {"path": path, "cum": cum, "stopT": stop_t}

# Auto-fit bounds to the geometry we actually render (stops + drawn shapes),
# so there is no dead margin. Pad slightly so edge dots aren't clipped.
lats = [s["lat"] for s in stops.values()]
lons = [s["lon"] for s in stops.values()]
for shape_list in route_shape_list.values():
    for shape in shape_list:
        for lat, lon in shape:
            lats.append(lat)
            lons.append(lon)

lat_pad = (max(lats) - min(lats)) * 0.015
lon_pad = (max(lons) - min(lons)) * 0.015
bounds = {
    "min_lat": round(min(lats) - lat_pad, 5),
    "max_lat": round(max(lats) + lat_pad, 5),
    "min_lon": round(min(lons) - lon_pad, 5),
    "max_lon": round(max(lons) + lon_pad, 5),
}

# Borough landmasses (for a basemap showing rivers + which borough is which).
# Heavily simplified outlines; water shows as the gaps between them.
def _simplify_ring(points, eps):
    """Decimate a [[lat,lon],...] ring: keep points >= eps apart (closed-ring safe)."""
    out = [points[0]]
    for p in points[1:]:
        lx, ly = out[-1]
        if ((p[0] - lx) ** 2 + (p[1] - ly) ** 2) ** 0.5 >= eps:
            out.append(p)
    if out[-1] != points[0]:
        out.append(points[0])  # keep it closed
    return out


boroughs = []
try:
    with open("data/boroughs.geojson") as f:
        gj = json.load(f)
    for feat in gj["features"]:
        name = feat["properties"].get("name", "")
        if name == "Staten Island":
            continue
        geom = feat["geometry"]
        polys = (
            geom["coordinates"]
            if geom["type"] == "MultiPolygon"
            else [geom["coordinates"]]
        )
        rings = []
        for poly in polys:
            ring = [[round(lat, 5), round(lon, 5)] for lon, lat in poly[0]]
            ring = _simplify_ring(ring, 0.0008)  # ~80m spacing
            if len(ring) >= 4:
                rings.append(ring)
        if not rings:
            continue
        big = max(rings, key=len)
        clat = sum(p[0] for p in big) / len(big)
        clon = sum(p[1] for p in big) / len(big)
        boroughs.append({"name": name, "rings": rings, "label": [round(clat, 5), round(clon, 5)]})
    print(
        f"Boroughs: {len(boroughs)} "
        f"({sum(len(r) for b in boroughs for r in b['rings'])} outline pts)"
    )
except FileNotFoundError:
    print("No data/boroughs.geojson - skipping basemap")

output = {
    "stops": list(stops.values()),
    "route_shapes": route_shape_list,
    "route_paths": route_paths,
    "route_colors": route_colors,
    "boroughs": boroughs,
    "bounds": bounds,
}

with open("static/map_data.json", "w") as f:
    json.dump(output, f)

print(f"Stops: {len(stops)}")
print(f"Routes: {len(route_shape_list)}")
print(f"Shapes: {sum(len(v) for v in route_shape_list.values())} total")
print(f"Bounds: {bounds}")
print(
    f"Route paths: {len(route_paths)} "
    f"(avg {round(sum(len(p['stopT']) for p in route_paths.values()) / max(1, len(route_paths)))} stops snapped each)"
)
print("Written to static/map_data.json")
