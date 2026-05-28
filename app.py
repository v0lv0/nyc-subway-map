import threading
import time as time_module
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify
from google.transit import gtfs_realtime_pb2

from stations import HOME, STATIONS

app = Flask(__name__)

FEEDS = {
    "ace": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
    "bdfm": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
    "g": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
    "jz": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
    "nqrw": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
    "l": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
    "1234567": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
    "si": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-si",
}

cache = {"trains": [], "updated": None}


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
    trains = []
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
            for stu in tu.stop_time_update:
                arr = stu.arrival.time if stu.arrival.time else stu.departure.time
                if arr and arr > time_module.time():
                    trains.append(
                        {
                            "trip_id": trip_id,
                            "route": route,
                            "stop_id": stu.stop_id,
                            "arrival": arr,
                            "direction": direction,
                        }
                    )
    cache["trains"] = trains
    cache["updated"] = datetime.now(timezone.utc).isoformat()
    print(f"Refreshed: {len(trains)} arrivals loaded")


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
                    arrivals.append(
                        {
                            "route": t["route"],
                            "stop_id": t["stop_id"],
                            "arrives_in_min": mins,
                            "direction": "Manhattan"
                            if suffix == "N"
                            else "Brooklyn"
                            if suffix == "S"
                            else "?",
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


if __name__ == "__main__":
    print("Starting initial fetch...")
    refresh_trains()
    t = threading.Thread(target=background_refresh, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000, debug=False)
