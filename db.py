import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "music.db"

# (name, value_type, min_value, max_value, allowed_values, default_value)
ATTRIBUTE_SEED = [
    ("agreeability",     "scalar",  0, 10, None,                                              5),
    ("country",          "scalar",  0, 10, None,                                              0),
    ("fun",              "boolean", None, None, None,                                         0),
    ("girliness",        "scalar",  0, 10, None,                                              0),
    ("happiness",        "scalar",  0, 10, None,                                              5),
    ("iconicness",       "scalar",  0, 10, None,                                              0),
    ("instrumentalness", "scalar",  0, 10, None,                                              0),
    ("intensity",        "scalar",  0, 10, None,                                              5),
    ("oldness",          "scalar",  0, 10, None,                                              0),
    ("pop",              "scalar",  0, 10, None,                                              0),
    ("rap",              "scalar",  0, 10, None,                                              0),
    ("rating",           "scalar",  1, 10, None,                                              None),
    ("roadtrip",         "boolean", None, None, None,                                         0),
    ("rock",             "scalar",  0, 10, None,                                              0),
    ("tempo",            "scalar",  0, 10, None,                                              5),
    ("tiktokness",       "scalar",  0, 10, None,                                              0),
    ("vaporwave",        "scalar",  0, 10, None,                                              0),
    ("voice_gender",     "enum",    None, None, json.dumps(["male", "female", "mixed", "none"]), None),
    ("workout",          "boolean", None, None, None,                                         0),
]

_ALLOWED_ATTRS = {row[0] for row in ATTRIBUTE_SEED}


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attributes (
                name           TEXT PRIMARY KEY,
                value_type     TEXT NOT NULL,
                min_value      REAL,
                max_value      REAL,
                allowed_values TEXT,
                default_value  TEXT
            )
        """)
        for row in ATTRIBUTE_SEED:
            conn.execute(
                "INSERT OR IGNORE INTO attributes VALUES (?,?,?,?,?,?)", row
            )

        attr_col_defs = _attr_column_defs(conn)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS songs (
                video_id         TEXT PRIMARY KEY,
                title            TEXT,
                artists          TEXT,
                album            TEXT,
                duration_seconds INTEGER,
                is_explicit      BOOLEAN DEFAULT 0,
                video_type       TEXT,
                view_count       INTEGER,
                in_library       BOOLEAN DEFAULT 0,
                liked            BOOLEAN DEFAULT 0,
                last_played      DATE,
                {attr_col_defs}
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_queries (
                name           TEXT PRIMARY KEY,
                expression     TEXT NOT NULL,
                yt_playlist_id TEXT
            )
        """)

        _apply_missing_attr_columns(conn)


def _attr_column_defs(conn):
    attrs = conn.execute(
        "SELECT name, value_type, default_value FROM attributes"
    ).fetchall()
    parts = []
    for a in attrs:
        if a["value_type"] == "boolean":
            col_type = "BOOLEAN"
        elif a["value_type"] == "scalar":
            col_type = "REAL"
        else:
            col_type = "TEXT"
        default = (
            f" DEFAULT {a['default_value']}"
            if a["default_value"] is not None
            else ""
        )
        parts.append(f"{a['name']} {col_type}{default}")
    return ",\n                ".join(parts)


def _apply_missing_attr_columns(conn):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(songs)")}
    attrs = conn.execute(
        "SELECT name, value_type, default_value FROM attributes"
    ).fetchall()
    for a in attrs:
        if a["name"] not in existing:
            if a["value_type"] == "boolean":
                col_type = "BOOLEAN"
            elif a["value_type"] == "scalar":
                col_type = "REAL"
            else:
                col_type = "TEXT"
            default = (
                f" DEFAULT {a['default_value']}"
                if a["default_value"] is not None
                else ""
            )
            conn.execute(
                f"ALTER TABLE songs ADD COLUMN {a['name']} {col_type}{default}"
            )


def upsert_songs(rows):
    """Upsert core song metadata. rows: list of dicts with song fields."""
    with _connect() as conn:
        for song in rows:
            core = {
                "video_id":         song["video_id"],
                "title":            song.get("title"),
                "artists":          song.get("artists"),
                "album":            song.get("album"),
                "duration_seconds": song.get("duration_seconds"),
                "is_explicit":      int(bool(song.get("is_explicit", False))),
                "video_type":       song.get("video_type"),
                "in_library":       int(bool(song.get("in_library", False))),
                "liked":            int(bool(song.get("liked", False))),
            }
            if "last_played" in song:
                core["last_played"] = song["last_played"]

            cols = list(core.keys())
            vals = [core[c] for c in cols]
            placeholders = ", ".join("?" * len(cols))
            update_clause = ", ".join(
                f"{c} = excluded.{c}" for c in cols if c != "video_id"
            )
            conn.execute(
                f"INSERT INTO songs ({', '.join(cols)}) VALUES ({placeholders})"
                f" ON CONFLICT(video_id) DO UPDATE SET {update_clause}",
                vals,
            )


def set_last_played(video_id, date_str):
    with _connect() as conn:
        conn.execute(
            "UPDATE songs SET last_played = ? WHERE video_id = ?",
            (date_str, video_id),
        )


def update_view_count(video_id, count):
    with _connect() as conn:
        conn.execute(
            "UPDATE songs SET view_count = ? WHERE video_id = ?",
            (count, video_id),
        )


def get_songs_missing_view_count():
    with _connect() as conn:
        return [
            r["video_id"]
            for r in conn.execute("SELECT video_id FROM songs WHERE view_count IS NULL")
        ]


def query_songs(expression=None):
    with _connect() as conn:
        if expression and expression.strip():
            sql = f"SELECT * FROM songs WHERE {expression}"
        else:
            sql = "SELECT * FROM songs"
        return [dict(r) for r in conn.execute(sql)]


def get_attributes():
    with _connect() as conn:
        return [
            dict(r)
            for r in conn.execute("SELECT * FROM attributes ORDER BY name")
        ]


def _check_attr(name):
    if name not in _ALLOWED_ATTRS:
        raise ValueError(f"Unknown attribute: {name!r}")


def update_song_attr(video_id, attr_name, value):
    _check_attr(attr_name)
    with _connect() as conn:
        conn.execute(
            f"UPDATE songs SET {attr_name} = ? WHERE video_id = ?",
            (value, video_id),
        )


def bulk_update_attr(video_ids, attr_name, value):
    _check_attr(attr_name)
    if not video_ids:
        return
    with _connect() as conn:
        placeholders = ", ".join("?" * len(video_ids))
        conn.execute(
            f"UPDATE songs SET {attr_name} = ? WHERE video_id IN ({placeholders})",
            [value, *video_ids],
        )


def get_saved_query(name):
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM saved_queries WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None


def save_query(name, expression):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO saved_queries (name, expression) VALUES (?, ?)"
            " ON CONFLICT(name) DO UPDATE SET expression = excluded.expression",
            (name, expression),
        )


def update_playlist_id(name, playlist_id):
    with _connect() as conn:
        conn.execute(
            "UPDATE saved_queries SET yt_playlist_id = ? WHERE name = ?",
            (playlist_id, name),
        )
