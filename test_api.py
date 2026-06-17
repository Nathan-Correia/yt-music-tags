"""
test_real_calls.py

Calls the actual ytmusicapi endpoints (with small limits, so it's fast and
doesn't dump your whole library) and prints what comes back, so we can
compare real output against the documented shapes before building real
sync/refresh logic.

Includes a playlist round-trip test: creates a brand-new throwaway playlist
("zz_test_delete_me"), inspects it, removes its one track, then deletes the
playlist again. This does NOT touch any of your existing playlists or library.

Usage:
    Run: python test_real_calls.py
    Paste back the full output.
"""

import json
import time

from ytmusicapi import YTMusic

AUTH_FILE = "browser.json"


def get_playlist_with_retry(yt, playlist_id, limit=None, attempts=5, delay_seconds=2):
    """
    Newly created playlists can take a moment to become browsable on
    YouTube's backend. get_playlist() can raise KeyError('contents') if
    called too soon after create_playlist(). Retry with a short delay
    instead of failing immediately.
    """
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return yt.get_playlist(playlist_id, limit=limit)
        except KeyError as e:
            last_error = e
            print(f"  attempt {attempt}/{attempts}: not ready yet ({e}), waiting {delay_seconds}s...")
            time.sleep(delay_seconds)
    raise last_error


def show(label, data):
    print("=" * 80)
    print(label)
    print("=" * 80)
    print(json.dumps(data, indent=2, default=str))
    print()


def main():
    yt = YTMusic(AUTH_FILE)

    # --- Library songs ---
    library_songs = yt.get_library_songs(limit=20)
    print(f"get_library_songs: returned {len(library_songs)} items, type={type(library_songs)}")
    show("get_library_songs - first item", library_songs[0] if library_songs else None)

    # --- Liked songs (check whether it's really a dict-with-tracks) ---
    liked = yt.get_liked_songs(limit=20)
    print(f"get_liked_songs: type={type(liked)}")
    if isinstance(liked, dict):
        print(f"  top-level keys: {list(liked.keys())}")
        tracks = liked.get("tracks", [])
        print(f"  'tracks' key has {len(tracks)} items")
        show("get_liked_songs - first track", tracks[0] if tracks else None)
    else:
        show("get_liked_songs - first item", liked[0] if liked else None)

    # --- Single song lookup, mainly to check for viewCount ---
    sample_video_id = library_songs[0]["videoId"] if library_songs else None
    if sample_video_id:
        song = yt.get_song(sample_video_id)
        video_details = song.get("videoDetails", {})
        show(f"get_song videoDetails for {sample_video_id}", video_details)

    # --- Safe playlist round trip on a throwaway test playlist ---
    if sample_video_id:
        print("Creating a throwaway test playlist...")
        playlist_id = yt.create_playlist(
            "zz_test_delete_me",
            "temporary test playlist, safe to delete",
            video_ids=[sample_video_id],
        )
        print(f"  created playlist id: {playlist_id}")

        fetched = get_playlist_with_retry(yt, playlist_id, limit=None)
        show("get_playlist on test playlist - tracks", fetched.get("tracks"))

        track = fetched["tracks"][0]
        print(f"  removing track via setVideoId={track.get('setVideoId')}")
        remove_result = yt.remove_playlist_items(playlist_id, [track])
        print(f"  remove_playlist_items result: {remove_result}")

        delete_result = yt.delete_playlist(playlist_id)
        print(f"  delete_playlist result: {delete_result}")


if __name__ == "__main__":
    main()