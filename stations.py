# Your home address — used for display only
HOME = "114 Leonard St, Brooklyn"

# Your stations — edit this list anytime to add/remove/reorder
# walk_min: estimated walking time from home
# stop_ids: MTA GTFS stop IDs (add N/S suffix for direction filtering, or leave without for both)
STATIONS = [
    {
        "name": "Lorimer St",
        "lines": ["L", "G"],
        "walk_min": 7,
        "stop_ids": ["L10", "G29"],
    },
    {
        "name": "Hewes St",
        "lines": ["J", "M"],
        "walk_min": 9,
        "stop_ids": ["M14"],
    },
    {
        "name": "Montrose Av",
        "lines": ["L"],
        "walk_min": 9,
        "stop_ids": ["L13"],
    },
    {
        "name": "Broadway",
        "lines": ["G"],
        "walk_min": 5,
        "stop_ids": ["G30"],
    },
]
