import threading
import time as time_module
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, send_from_directory
from google.transit import gtfs_realtime_pb2

from stations import HOME, STATIONS

app = Flask(__name__)
app = Flask(__name__, static_folder="static", static_url_path="/static")
FEEDS = {
    "ace": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
    "bdfm": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
    "g": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
    "jz": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
    "nqrw": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
    "l": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
    "1234567": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
}

cache = {"trains": [], "vehicles": [], "updated": None}


@app.after_request
def no_cache(resp):
    # Wall display reloads should always pull fresh JS/data, never a stale cache.
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def _base(stop_id):
    """Strip the N/S platform suffix to get the parent station id."""
    return stop_id[:-1] if stop_id and stop_id[-1] in ("N", "S") else stop_id


def fetch_feed(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(r.content)
        return feed
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def refresh_trains():
    now = time_module.time()
    trains = []
    trips = []  # per active train: ordered stop list + future arrivals
    sequences = {}  # (route, suffix) -> longest ordered list of parent stop ids
    for name, url in FEEDS.items():
        feed = fetch_feed(url)
        if not feed:
            continue
        for entity in feed.entity:
            if not entity.HasField("trip_update"):
                continue
            tu = entity.trip_update
            route = tu.trip.route_id
            trip_id = tu.trip.trip_id
            direction = tu.trip.direction_id

            order = []  # all parent stops in travel order (for canonical sequence)
            future = []  # (parent_stop, arrival) still ahead of now
            suffix = None
            for stu in tu.stop_time_update:
                sid = stu.stop_id
                if not sid:
                    continue
                if sid[-1] in ("N", "S"):
                    suffix = sid[-1]
                order.append(_base(sid))
                arr = stu.arrival.time if stu.arrival.time else stu.departure.time
                if arr and arr > now:
                    trains.append(
                        {
                            "trip_id": trip_id,
                            "route": route,
                            "stop_id": sid,
                            "arrival": arr,
                            "direction": direction,
                        }
                    )
                    future.append((_base(sid), arr))

            if not future:
                continue
            key = (route, suffix)
            if len(order) > len(sequences.get(key, [])):
                sequences[key] = order
            trips.append(
                {"id": trip_id, "route": route, "key": key, "future": future}
            )

    # Build one moving "vehicle" per train: its next stop, when it arrives, the
    # stop it's coming from (via the canonical sequence), and a segment-time
    # estimate so the frontend can interpolate its position along the track.
    vehicles = []
    for tp in trips:
        nxt_stop, nxt_arr = tp["future"][0]
        if len(tp["future"]) >= 2:
            seg_time = tp["future"][1][1] - nxt_arr
        else:
            seg_time = 90
        seg_time = max(30, min(300, seg_time))
        seq = sequences.get(tp["key"], [])
        prev_stop = None
        if nxt_stop in seq:
            i = seq.index(nxt_stop)
            if i > 0:
                prev_stop = seq[i - 1]
        vehicles.append(
            {
                "id": tp["id"],
                "route": tp["route"],
                "prev": prev_stop,
                "next": nxt_stop,
                "next_arr": nxt_arr,
                "seg_time": seg_time,
            }
        )

    cache["trains"] = trains
    cache["vehicles"] = vehicles
    cache["updated"] = datetime.now(timezone.utc).isoformat()
    print(f"Refreshed: {len(trains)} arrivals, {len(vehicles)} vehicles")


def background_refresh():
    while True:
        time_module.sleep(30)
        refresh_trains()


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "trains_cached": len(cache["trains"]),
            "updated": cache["updated"],
        }
    )


@app.route("/api/trains")
def get_trains():
    return jsonify(cache)


@app.route("/api/vehicles")
def get_vehicles():
    return jsonify({"vehicles": cache["vehicles"], "updated": cache["updated"]})


@app.route("/api/trains/<stop_id>")
def get_trains_for_stop(stop_id):
    now = time_module.time()
    upcoming = [
        t for t in cache["trains"] if t["stop_id"] == stop_id and t["arrival"] > now
    ]
    upcoming.sort(key=lambda x: x["arrival"])
    return jsonify(
        {"stop_id": stop_id, "arrivals": upcoming[:10], "updated": cache["updated"]}
    )


# Direction label per route by N/S suffix (N = railroad-north / first-listed).
# Default is Manhattan/Brooklyn; override where that's wrong for your lines.
DIR_LABELS = {
    "G": {"N": "Queens", "S": "Brooklyn"},
    "J": {"N": "Manhattan", "S": "Queens"},
    "Z": {"N": "Manhattan", "S": "Queens"},
    "M": {"N": "Manhattan", "S": "Queens"},
}
DEFAULT_DIR = {"N": "Manhattan", "S": "Brooklyn"}


@app.route("/api/stations")
def get_stations():
    now = time_module.time()
    result = []
    for station in STATIONS:
        arrivals = []
        for t in cache["trains"]:
            if any(t["stop_id"].startswith(sid) for sid in station["stop_ids"]):
                if t["arrival"] > now:
                    mins = round((t["arrival"] - now) / 60)
                    suffix = t["stop_id"][-1] if t["stop_id"][-1] in ("N", "S") else "?"
                    labels = DIR_LABELS.get(t["route"], DEFAULT_DIR)
                    arrivals.append(
                        {
                            "route": t["route"],
                            "stop_id": t["stop_id"],
                            "arrives_in_min": mins,
                            "direction": labels.get(suffix, "?"),
                        }
                    )
        arrivals.sort(key=lambda x: x["arrives_in_min"])
        result.append(
            {
                "name": station["name"],
                "lines": station["lines"],
                "walk_min": station["walk_min"],
                "arrivals": arrivals[:6],
            }
        )
    return jsonify({"home": HOME, "stations": result, "updated": cache["updated"]})


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


if __name__ == "__main__":
    print("Starting initial fetch...")
    refresh_trains()
    t = threading.Thread(target=background_refresh, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000, debug=False)
