// Live-data config for the serverless (static) build. Mirrors stations.py and
// the FEEDS / DIR_LABELS constants in app.py. Edit stations here the same way
// you would in stations.py. (app.py still reads its own copy for local dev.)

window.HOME = "114 Leonard St, Brooklyn";

// Your stations — name, line badges, walk time, and MTA GTFS parent stop ids.
window.STATIONS = [
  { name: "Lorimer St",  lines: ["L", "G"], walk_min: 7, stop_ids: ["L10", "G29"] },
  { name: "Hewes St",    lines: ["J", "M"], walk_min: 9, stop_ids: ["M14"] },
  { name: "Montrose Av", lines: ["L"],      walk_min: 9, stop_ids: ["L13"] },
  { name: "Broadway",    lines: ["G"],      walk_min: 5, stop_ids: ["G30"] },
];

// MTA GTFS-realtime feeds (CORS-open, no API key needed as of 2026).
window.FEEDS = {
  ace:  "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
  bdfm: "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
  g:    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
  jz:   "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
  nqrw: "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
  l:    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
  "1234567": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
};

// Direction label per route by N/S suffix (N = railroad-north / first-listed).
window.DIR_LABELS = {
  G: { N: "Queens",    S: "Brooklyn" },
  J: { N: "Manhattan", S: "Queens" },
  Z: { N: "Manhattan", S: "Queens" },
  M: { N: "Manhattan", S: "Queens" },
};
window.DEFAULT_DIR = { N: "Manhattan", S: "Brooklyn" };
