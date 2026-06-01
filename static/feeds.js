// Browser-side GTFS-realtime client. Replaces the Flask /api layer so the
// dashboard runs as a pure static site (e.g. GitHub Pages): it fetches MTA's
// feeds directly (they're CORS-open and keyless), decodes the protobuf with
// protobuf.js, and reshapes it into the same {stations, vehicles} the frontend
// already consumes. This is a 1:1 port of app.py's refresh_trains/get_stations.
//
// Minimal subset of the GTFS-realtime schema — just the fields we read. Unknown
// fields in the real feed are skipped by the protobuf wire decoder.
const GTFS_PROTO = `
syntax = "proto2";
message FeedMessage { optional FeedHeader header = 1; repeated FeedEntity entity = 2; }
message FeedHeader { optional string gtfs_realtime_version = 1; optional uint64 timestamp = 3; }
message FeedEntity { optional string id = 1; optional TripUpdate trip_update = 3; }
message TripUpdate { optional TripDescriptor trip = 1; repeated StopTimeUpdate stop_time_update = 2; }
message TripDescriptor { optional string trip_id = 1; optional string route_id = 5; optional uint32 direction_id = 6; }
message StopTimeUpdate { optional uint32 stop_sequence = 1; optional StopTimeEvent arrival = 2; optional StopTimeEvent departure = 3; optional string stop_id = 4; }
message StopTimeEvent { optional int64 time = 2; }
`;

let _FeedMessage = null;
function feedType() {
  if (!_FeedMessage) {
    const root = protobuf.parse(GTFS_PROTO, { keepCase: true }).root;
    _FeedMessage = root.lookupType("FeedMessage");
  }
  return _FeedMessage;
}

// int64 fields decode to a Long object (or a plain number); normalize to number.
function num(v) {
  if (v == null) return 0;
  return (typeof v === "object" && v.toNumber) ? v.toNumber() : Number(v);
}
// Strip the N/S platform suffix to get the parent station id.
function baseStop(sid) {
  const c = sid && sid[sid.length - 1];
  return (c === "N" || c === "S") ? sid.slice(0, -1) : sid;
}

async function fetchFeed(url, FeedMessage) {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    return FeedMessage.decode(new Uint8Array(await r.arrayBuffer()));
  } catch (e) {
    console.warn("feed fetch failed", url, e);
    return null;
  }
}

// Build flat arrivals + one moving "vehicle" per active train (its next stop,
// the stop it's coming from via the canonical sequence, and a segment-time
// estimate so the frontend can interpolate position along the track).
async function refresh() {
  const FeedMessage = feedType();
  const now = Date.now() / 1000;
  const trains = [];
  const trips = [];
  const sequences = {}; // (route|suffix) -> longest ordered parent-stop list
  const feeds = await Promise.all(
    Object.values(FEEDS).map((u) => fetchFeed(u, FeedMessage))
  );
  for (const feed of feeds) {
    if (!feed) continue;
    for (const entity of feed.entity) {
      const tu = entity.trip_update;
      if (!tu || !tu.trip) continue;
      const route = tu.trip.route_id || "";
      const tripId = tu.trip.trip_id || "";
      const direction = tu.trip.direction_id || 0;
      const order = [];
      const future = [];
      let suffix = null;
      for (const stu of tu.stop_time_update || []) {
        const sid = stu.stop_id;
        if (!sid) continue;
        const c = sid[sid.length - 1];
        if (c === "N" || c === "S") suffix = c;
        order.push(baseStop(sid));
        const arr =
          num(stu.arrival && stu.arrival.time) ||
          num(stu.departure && stu.departure.time);
        if (arr && arr > now) {
          trains.push({ trip_id: tripId, route, stop_id: sid, arrival: arr, direction });
          future.push([baseStop(sid), arr]);
        }
      }
      if (!future.length) continue;
      const key = route + "|" + suffix;
      if (order.length > (sequences[key] || []).length) sequences[key] = order;
      trips.push({ id: tripId, route, key, future });
    }
  }

  const vehicles = [];
  for (const tp of trips) {
    const [nxtStop, nxtArr] = tp.future[0];
    let segTime = tp.future.length >= 2 ? tp.future[1][1] - nxtArr : 90;
    segTime = Math.max(30, Math.min(300, segTime));
    const seq = sequences[tp.key] || [];
    let prevStop = null;
    const i = seq.indexOf(nxtStop);
    if (i > 0) prevStop = seq[i - 1];
    vehicles.push({
      id: tp.id, route: tp.route, prev: prevStop,
      next: nxtStop, next_arr: nxtArr, seg_time: segTime,
    });
  }
  return { trains, vehicles, updated: new Date().toISOString() };
}

// Per configured station: upcoming arrivals with the walk-aware fields the UI
// needs. Mirror of app.py get_stations().
function stationsView(data) {
  const now = Date.now() / 1000;
  const stations = STATIONS.map((st) => {
    const arrivals = [];
    for (const t of data.trains) {
      if (!st.stop_ids.some((sid) => t.stop_id.startsWith(sid))) continue;
      if (t.arrival <= now) continue;
      const mins = Math.round((t.arrival - now) / 60);
      const c = t.stop_id[t.stop_id.length - 1];
      const suffix = c === "N" || c === "S" ? c : "?";
      const labels = DIR_LABELS[t.route] || DEFAULT_DIR;
      arrivals.push({
        route: t.route, stop_id: t.stop_id,
        arrives_in_min: mins, direction: labels[suffix] || "?",
      });
    }
    arrivals.sort((a, b) => a.arrives_in_min - b.arrives_in_min);
    return { name: st.name, lines: st.lines, walk_min: st.walk_min, arrivals: arrivals.slice(0, 12) };
  });
  return { home: HOME, stations, updated: data.updated };
}

window.MTA = { refresh, stationsView };
