import requests
from flask import Flask, jsonify
from google.transit import gtfs_realtime_pb2
from datetime import datetime
import threading
import time

app = Flask(__name__)

# MTA GTFS-RT feed URLs (no API key needed)
FEEDS = {
    "ace":    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
    "bdfm":   "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
    "g":      "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
    "jz":     "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
    "nqrw":   "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
    "l":      "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
    "1234567":"https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
    "si":     "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-si",
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
            direction = tu.trip.direction_id  # 0=north, 1=south

            for stu in tu.stop_time_update:
                arr = stu.arrival.time if stu.arrival.time else stu.departure.time
                if arr and arr > time.time():
                    trains.append({
                        "trip_id": trip_id,
                        "route": route,
                        "stop_id": stu.stop_id,
                        "arrival": arr,
                        "direction": direction,
                    })

    cache["trains"] = trains
    cache["updated"] = datetime.utcnow().isoformat()
    print(f"Refreshed: {len(trains)} arrivals loaded")

def background_refresh():
    while True:
        refresh_trains()
        time.sleep(30)

@app.route("/api/trains")
def get_trains():
    return jsonify(cache)

@app.route("/api/trains/<stop_id>")
def get_trains_for_stop(stop_id):
    now = time.time()
    upcoming = [
        t for t in cache["trains"]
        if t["stop_id"] == stop_id and t["arrival"] > now
    ]
    upcoming.sort(key=lambda x: x["arrival"])
    return jsonify({"stop_id": stop_id, "arrivals": upcoming[:10], "updated": cache["updated"]})

@app.route("/health")
def health():
    return jsonify({"status": "ok", "trains_cached": len(cache["trains"]), "updated": cache["updated"]})

if __name__ == "__main__":
    print("Starting initial fetch...")
    refresh_trains()
    t = threading.Thread(target=background_refresh, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000, debug=False)
