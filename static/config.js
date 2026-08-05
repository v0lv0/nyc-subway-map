// Static config for the serverless build. No personal data lives here — your
// home and stations are passed at runtime via URL parameters:
//
//   ?home=LAT,LON           e.g. ?home=40.7074,-73.9464     (short alias: ?h=)
//   ?home=<address>         e.g. ?home=350 5th Ave, New York (geocoded)
//   ?addr=<label>           display label for the address bar (alias: ?a=)
//   ?stops=ID1-ID2,ID3,...  station cards; join a transfer complex with '-'
//                           e.g. ?stops=L10-G29,M14,L13,G30 (alias: ?s=)
//   ?reset                  forget the remembered config (below) and start clean
//
// The resolved config is saved in the browser's localStorage, so the URL only has
// to be typed once — after that the bare site URL restores the same dashboard.
// That keeps your address out of this repo AND off the URL bar; it lives only in
// the browser you typed it into. Params override the saved value field by field.
//
// Parsing is deliberately forgiving, because this URL gets typed on a TV remote:
// param names are lowercased and whitespace-stripped ("st ops" still works), stop
// ids are uppercased, and a complex can be joined with any of - _ + . | or a
// space (a raw '+' in a URL decodes to a space, which is why '-' is now shown).
//
// If ?stops is omitted, the nearest stations to home are chosen automatically.
// If ?home is omitted, the map centres on the given stops.
// If nothing is passed, the neutral default below is used (no personal info).

window.DEFAULTS = {
  addr: "Times Sq, Manhattan",
  home: [40.7559, -73.9870],
  stops: [],          // [] => auto-pick nearest NUM_STATIONS to home
};
window.NUM_STATIONS = 4;     // how many station cards when stops are auto-picked
window.WALK_MPM = 80;        // walking speed (metres/min) for the walk-time estimate

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
