# Local-dev config for app.py (the Flask fallback). The deployed static site
# does NOT use this — it reads home + stations from URL params (see static/
# config.js). Neutral defaults here so no personal info lives in the repo.
HOME = "Times Sq, Manhattan"

# walk_min: estimated walking time from home
# stop_ids: MTA GTFS stop IDs (add N/S suffix for direction filtering, or leave without for both)
STATIONS = [
    {
        "name": "Times Sq-42 St",
        "lines": ["1", "2", "3", "7", "N", "Q", "R", "W"],
        "walk_min": 2,
        "stop_ids": ["127", "725", "R16"],
    },
    {
        "name": "42 St-Port Authority",
        "lines": ["A", "C", "E"],
        "walk_min": 4,
        "stop_ids": ["A27"],
    },
]
