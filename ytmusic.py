import json
import time
from datetime import date, timedelta
from pathlib import Path

import db

BROWSER_JSON = Path(__file__).parent / "browser.json"


def _ytm():
    from ytmusicapi import YTMusic
    return YTMusic(str(BROWSER_JSON))


def _parse_played(label, sync_date):
    """Convert a relative history label like 'Today'/'Yesterday' to ISO date."""
    normalized = label.strip().lower()
    if normalized == "today":
        return sync_date.isoformat()
    if normalized == "yesterday":
        return (sync_date - timedelta(days=1)).isoformat()
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if normalized in day_names:
        target_wd = day_names.index(normalized)
        current_wd = sync_date.weekday()
        days_ago = (current_wd - target_wd) % 7 or 7
        return (sync_date - timedelta(days=days_ago)).isoformat()
    return None


def _map_track(item, in_library=False, liked=False):
    artists = [a["name"] for a in (item.get("artists") or [])]
    album_node = item.get("album") or {}
    return {
        "video_id":         item["videoId"],
        "title":            item.get("title"),
        "artists":          json.dumps(artists),
        "album":            album_node.get("name") if isinstance(album_node, dict) else None,
        "duration_seconds": item.get("duration_seconds"),
        "is_explicit":      item.get("isExplicit", False),
        "video_type":       item.get("videoType"),
        "in_library":       in_library,
        "liked":            liked,
    }


def sync():
    """
    Pull library songs, liked songs, and play history into the local DB.
    Returns the total number of distinct songs upserted.
    """
    ytm = _ytm()
    today = date.today()
    songs = {}

    for item in ytm.get_library_songs(limit=10000):
        mapped = _map_track(item, in_library=True)
        vid = mapped["video_id"]
        if vid in songs:
            songs[vid]["in_library"] = True
        else:
            songs[vid] = mapped

    liked_result = ytm.get_liked_songs(limit=10000)
    for item in liked_result.get("tracks", []):
        mapped = _map_track(item, liked=True)
        vid = mapped["video_id"]
        if vid in songs:
            songs[vid]["liked"] = True
        else:
            songs[vid] = mapped

    db.upsert_songs(list(songs.values()))

    # History — deduplicate to first (most-recent) occurrence per videoId
    seen_vids = set()
    for item in ytm.get_history():
        vid = item.get("videoId")
        if not vid or vid in seen_vids:
            continue
        seen_vids.add(vid)
        played_date = _parse_played(item.get("played", ""), today)
        if played_date:
            db.set_last_played(vid, played_date)

    return len(songs)


def enrich_batch(video_ids, on_progress, should_stop):
    """
    Fetch view counts for each video_id in the list.
    on_progress(): called after each attempt (success or failure).
    should_stop(): callable that returns True when a stop has been requested.
    """
    ytm = _ytm()
    for vid in video_ids:
        if should_stop():
            break
        try:
            result = ytm.get_song(vid)
            vc_str = result.get("videoDetails", {}).get("viewCount")
            if vc_str is not None:
                db.update_view_count(vid, int(vc_str))
        except Exception:
            pass
        time.sleep(0.15)
        on_progress()


def _get_playlist_tracks(ytm, playlist_id, retries=4, delay=2.0):
    """Fetch playlist tracks, retrying on the 'contents' KeyError that occurs
    right after playlist creation before YouTube finishes indexing it."""
    last_exc = None
    for attempt in range(retries):
        try:
            result = ytm.get_playlist(playlist_id, limit=None)
            return result.get("tracks") or []
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(delay)
    raise last_exc


def create_or_refresh_playlist(name, expression):
    """
    Evaluate expression against the local songs table, then create or
    refresh-in-place the matching YouTube Music playlist.
    Returns (playlist_id, action) where action is 'created' or 'refreshed'.
    """
    ytm = _ytm()

    songs = db.query_songs(expression or None)
    video_ids = [s["video_id"] for s in songs]

    # Check saved_queries first, then fall back to scanning library playlists
    saved = db.get_saved_query(name)
    playlist_id = saved["yt_playlist_id"] if saved else None

    if not playlist_id:
        for pl in ytm.get_library_playlists(limit=None):
            if pl.get("title") == name:
                playlist_id = pl["playlistId"]
                break

    db.save_query(name, expression or "")

    if playlist_id:
        current_tracks = _get_playlist_tracks(ytm, playlist_id)
        if current_tracks:
            ytm.remove_playlist_items(playlist_id, current_tracks)
        if video_ids:
            ytm.add_playlist_items(playlist_id, video_ids)
        db.update_playlist_id(name, playlist_id)
        return playlist_id, "refreshed"

    result = ytm.create_playlist(name, "", video_ids=video_ids)
    if not isinstance(result, str):
        raise RuntimeError(f"create_playlist returned unexpected value: {result!r}")
    db.update_playlist_id(name, result)
    return result, "created"
