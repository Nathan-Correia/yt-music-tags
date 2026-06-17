# YouTube Music Tag Organizer — Project Spec

## Overview

A personal, local tool that replaces YouTube Music playlists with freeform tagging. Instead of sorting songs into separate playlists, every song gets any number of tags and attributes (some boolean, some 1-10 scalars, some categorical). The user writes saved queries — plain SQL filter/sort fragments — and the tool generates or refreshes a real playlist in the user's YouTube Music account from the query results.

This is a single-user, local-only tool. It is not going to be distributed or shipped to other users, so it doesn't need multi-user support, auth flows beyond the user's own account, or production-grade hardening — just correctness and maintainability for one person's use.

## Tech stack / environment

- Python
- `ytmusicapi` (already installed and configured by the user)
- Auth: use `browser.json` (cookie-based browser auth).
- SQLite for local storage (single file, no external DB server)
- A small local web app: Flask backend, plain HTML/CSS/JS frontend. CSS and JS live in their own files, not inlined in the HTML. Visual style: minimal, dark theme, darkish green accents.

## Data model

### `songs` table

One row per song, keyed by YouTube `videoId`. This table holds both the core metadata columns and every custom attribute as a real column.

**Core columns:**

| column | type | source |
|---|---|---|
| video_id | TEXT (PK) | from any ytmusicapi call |
| title | TEXT | library/liked/playlist responses |
| artists | TEXT (JSON list of names) | library/liked/playlist responses |
| album | TEXT | library/liked/playlist responses |
| duration_seconds | INTEGER | library/liked/playlist responses |
| is_explicit | BOOLEAN | library/liked/playlist responses |
| video_type | TEXT | e.g. `MUSIC_VIDEO_TYPE_ATV`, `MUSIC_VIDEO_TYPE_OMV` |
| view_count | INTEGER, nullable | from `get_song(videoId)["videoDetails"]["viewCount"]`, populated via background enrichment, not part of the main sync |
| in_library | BOOLEAN | true if returned by `get_library_songs` |
| liked | BOOLEAN | true if returned by `get_liked_songs` |
| last_played | DATE, nullable | derived from `get_history()`, called as part of sync (see workflow below) |

**Attribute columns** (one real column per row in the `attributes` registry below):

| column | type | default |
|---|---|---|
| rating | REAL, nullable | none — manual, never defaulted |
| tiktokness | REAL | 0 |
| girliness | REAL | 0 |
| iconicness | REAL | 0 |
| agreeability | REAL | 5 |
| tempo | REAL | 5 |
| oldness | REAL | 0 |
| happiness | REAL | 5 |
| instrumentalness | REAL | 0 |
| intensity | REAL | 5 |
| pop | REAL | 0 |
| rock | REAL | 0 |
| rap | REAL | 0 |
| vaporwave | REAL | 0 |
| country | REAL | 0 |
| voice_gender | TEXT, nullable | none — manual enum |
| workout | BOOLEAN | 0 |
| roadtrip | BOOLEAN | 0 |
| fun | BOOLEAN | 0 |

**Default rationale:** attributes split into three groups. Group one (`tiktokness`, `girliness`, `iconicness`, `oldness`, `instrumentalness`, all five genre scores, and the three booleans) tracks a distinctive quality most songs simply don't have, so 0 is an honest "doesn't have this" default. Group two (`agreeability`, `tempo`, `happiness`, `intensity`) is a true spectrum where every song sits somewhere, so there's no meaningful "absence" — the midpoint (5) is the least-wrong guess and keeps untagged songs out of both the high and low ends of a filter. Group three (`rating`, `voice_gender`) stays NULL with no default, since both are explicitly manual and a missing value is meaningfully different from a measured low one. This matters because of SQL's three-valued logic: `NOT (x > 3)` evaluates to NULL, not TRUE, when `x` is NULL, so an un-defaulted column would silently drop untagged songs out of negated filters — the defaults above were chosen specifically to avoid that trap for the attributes where it would give a wrong answer.

### `attributes` table (registry)

Used to drive the tagging UI (so it knows whether to render a slider, a checkbox, or a dropdown for a given attribute) and to drive the migration step when a new attribute gets added.

| column | type |
|---|---|
| name | TEXT (PK) — must match the corresponding `songs` column name exactly, snake_case, no hyphens |
| value_type | TEXT: `scalar`, `boolean`, or `enum` |
| min_value | REAL, nullable (for scalar) |
| max_value | REAL, nullable (for scalar) |
| allowed_values | TEXT, nullable (JSON list, for enum) |
| default_value | REAL/TEXT, nullable — the default used both as the SQLite column default and to backfill existing rows when the attribute is added |

Adding a new attribute is now a two-step process: insert a row here, then run the corresponding `ALTER TABLE songs ADD COLUMN <name> <type> DEFAULT <default_value>` against `songs`. SQLite handles this instantly even on an existing table.

Seed this table with the current attribute list:

**Scalar, 1-10:** `rating` (default none), `tiktokness` (0), `girliness` (0), `iconicness` (0), `agreeability` (5), `tempo` (5), `oldness` (0, how dated/retro it feels, independent of actual release date), `happiness` (5), `instrumentalness` (0), `intensity` (5)

**Scalar, 1-10, genre-as-degree (not boolean — a song can score on multiple):** `pop` (0), `rock` (0), `rap` (0), `vaporwave` (0), `country` (0)

**Enum, manual:** `voice_gender` (default none)

**Boolean:** `workout` (0), `roadtrip` (0), `fun` (0)

### `saved_queries` table

| column | type |
|---|---|
| name | TEXT (PK) — also used as the YouTube Music playlist title |
| expression | TEXT — the literal SQL fragment typed into the UI's single filter/sort bar, run directly against `songs` |
| yt_playlist_id | TEXT, nullable — populated once the playlist has been created on YouTube Music |

Even though there's no UI yet to browse or reload past saved queries (deferred — see below), this table and the lookup it enables are still required for the MVP: every time "create playlist" is pressed, the backend needs to check this table (or fall back to `get_library_playlists` by title) for an existing playlist with that name, so it can refresh-in-place instead of calling `create_playlist` again. Skipping this check is what trips the playlist-creation rate limit the moment the same name gets pushed twice.

## Core workflows

### 1. Sync

Triggered only by an explicit "Sync" button in the UI — never automatically, and never on any periodic or scheduled cadence. On page load, nothing has been fetched yet; the local `songs` table is only touched when this button is pressed.

- `get_library_songs(limit=<large number, e.g. 10000>)` — returns a plain list. Note: this method's `limit` param is a plain `int`, not `Optional[int]`, so there's no "get everything" flag — pass a number comfortably larger than the library.
- `get_liked_songs(limit=<large number>)` — returns a **dict**, not a list. The actual tracks are under `result["tracks"]`.
- Upsert both sources into `songs` by `video_id`, setting `in_library`/`liked` flags appropriately (a song can be in one, both, or neither — library songs and liked songs are separate concepts in YouTube Music). New rows get every attribute column initialized to its registry default, so a freshly-synced song is "untagged" in a well-defined way from the start rather than a row full of bare NULLs.
- Also call `get_history()` as part of this same sync — there's no separate trigger or schedule for history specifically. It has no `limit` or pagination support; it returns a single fixed batch (observed: ~199-200 items), in reverse chronological order, **deduplicated to one entry per song** (no way to recover play counts from repeats). For each entry, convert its relative `played` label (`"Today"`, `"Yesterday"`, etc.) to an absolute date using the date the sync runs, then write it straight into `last_played` — just overwrite, no need to compare against the existing value or keep any history of our own beyond this single column. Songs outside this rolling ~200-item window simply keep whatever `last_played` they already had from a previous sync (possibly stale) until a future sync happens to include them again, which is fine since only relatively recent plays matter here.

### 2. Metadata enrichment

Triggered only by its own explicit button in the UI, separate from Sync — never automatic, never periodic.

- For each song missing a `view_count`, call `get_song(video_id)` and read `response["videoDetails"]["viewCount"]` (returned as a string — cast to int).
- This is a **per-song call with no batch equivalent**, so once started it runs as a loop with a small delay between calls. Empirical testing showed zero failures across 500 consecutive `get_song()` calls with no artificial delay at all, sustaining ~8.4 calls/sec (bound mainly by normal network latency, not by anything YouTube was throttling) — a conservative delay like 0.1–0.2s per call is plenty safe at this scale. Revisit with a longer test run if the real library turns out to be much larger than 500 songs, since this hasn't been confirmed over a longer sustained run or against any per-hour-style cap.
- While running, the UI shows live progress as "x of y songs complete." A "Stop" button halts the loop after the in-flight call finishes — no need to resume from an exact position, since the next run simply picks up whatever songs are still missing a `view_count`.

### 3. Tagging

Happens directly on the single-page UI's results list (see "UI design" below): inline editable cells for each attribute column, plus a multi-select + bulk-apply control for setting one attribute to one value across several selected songs at once. Tagging fatigue is the real bottleneck of this whole project, so the bulk-apply path matters as much as the single-cell path.

### 4. Query evaluation + playlist refresh

- A saved query is a SQL filter/sort fragment, run directly against the local `songs` table (no join or view needed now that attributes are real columns, and no call to ytmusicapi — querying only ever hits the local database) to produce a list of `video_id`s.
- To sync that result to YouTube Music:
  1. If `yt_playlist_id` is already known, use it. Otherwise check `get_library_playlists(limit=None)` for a playlist whose title matches the saved query's name.
  2. **If the playlist already exists:** fetch its current tracks with `get_playlist(playlist_id, limit=None)`, call `remove_playlist_items(playlist_id, current_tracks)` to clear it (each item needs both `videoId` and `setVideoId`, which only `get_playlist` provides), then `add_playlist_items(playlist_id, new_video_ids)` to refill it.
  3. **If it doesn't exist yet:** create it directly with `create_playlist(title, description, video_ids=new_video_ids)`, and store the returned id in `yt_playlist_id`.
- Always prefer this refresh-in-place pattern over creating a fresh playlist on every run — YouTube enforces a rate limit specifically on playlist *creation* (`429 RESOURCE_EXHAUSTED`, "creating too many playlists") that refreshing in place avoids entirely. This check runs on every "create playlist" press regardless of name, not just for names the user has explicitly revisited.
- Refresh is manual only: there is no scheduled or background job. The only way a playlist gets refreshed is the user pressing the "Create playlist" button on the page again with a matching name.

## UI design

Single page, minimal, dark theme with darkish green accents. On page load, nothing is fetched or shown automatically — the results list starts empty until the user presses "Sync" and/or "Go."

- **Sync button**: triggers the Sync workflow above (pulls library songs, liked songs, and recent history from YouTube Music into the local database). This is the only path by which the local DB gets updated from YouTube — no automatic or periodic syncing happens anywhere else in the app.
- **Metadata enrichment button**: starts the `get_song()` view-count pass described above, separately from Sync. While running it shows progress as "x of y songs complete," and has its own "Stop" button to halt the loop after the in-flight call finishes. Like Sync, this never runs on its own — only when pressed.
- **Filter/sort bar** at the top: a single free-text field that takes any raw SQL fragment, substituted directly after `WHERE` in the underlying query (so it can include both a condition and an `ORDER BY` in the same string), plus a "Go" button. Pressing it runs the query against the local `songs` table only (never ytmusicapi, which keeps it fast regardless of library size) and re-renders the results list below. An empty filter returns everything via a plain `SELECT *` with no `WHERE`/`ORDER BY` — whatever order SQLite hands back is accepted as-is for now; not engineered for a guaranteed order in v1, revisit only if it turns out to be unreliable in practice.
- **Malformed SQL** in the filter bar is caught and shown as an inline error message near the bar, rather than crashing the page or silently returning nothing.
- **Results list** below the bar: one row per matching song, with every attribute shown as an inline editable cell (click/edit a cell, it saves — on blur or immediately, implementation's choice).
- **Row selection**: checkboxes per row plus a small bulk-edit control ("set [attribute] to [value] for selected") to address batch tagging directly.
- **Create playlist**: a text input for the playlist/query name plus a button. Pressing it evaluates the current filter, runs the saved-query lookup described above, and either refreshes the matching playlist in place or creates a new one.

## Known ytmusicapi gotchas (verified against real API responses during development — please respect these rather than re-discovering them)

- `get_liked_songs` returns a dict with a `tracks` key, not a list — easy to miss.
- `get_history` has no `limit`/pagination parameter; it returns one fixed batch only.
- `get_history` entries only have a relative `played` label (`"Today"`, `"Yesterday"`, etc.), never an exact timestamp, and are already deduplicated to one entry per song.
- `get_playlist` requires `limit=None` to retrieve all tracks (default is 100).
- A playlist fetched via `get_playlist` immediately after `create_playlist` can raise `KeyError: 'contents'` because YouTube hasn't finished indexing the new playlist yet. **Wrap the first `get_playlist` call on a newly created playlist in a retry loop with a short delay** (a few attempts, ~2 seconds apart, is sufficient based on testing).
- `remove_playlist_items` requires each item to include both `videoId` and `setVideoId` — `setVideoId` is only available from `get_playlist`'s track output, not from library/liked/search results.
- `add_playlist_items` defaults to `duplicates=False`, which means **the entire call fails and adds nothing** if any of the given videos are already in the playlist — not a silent skip. The refresh-in-place pattern avoids this since the playlist is cleared first.
- `create_playlist` returns the playlist ID as a string on success, or a full response dict if something went wrong — check the type of the return value.
- `delete_playlist` doesn't return a clean status string in practice — treat "no exception raised" as success rather than parsing its return value.
- `get_song`'s useful metadata (including `viewCount`) lives under `response["videoDetails"]`, not at the top level.
