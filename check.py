#!/usr/bin/env python3
"""
YouTube Music Library Embeddability Checker
=============================================

Pulls your YouTube Music library (saved library songs + liked songs) via the
unofficial `ytmusicapi`, then checks every track against the OFFICIAL YouTube
Data API v3 to see which ones can actually be played in an embedded IFrame
player vs which ones the owner has blocked from embedding, or region-locked
out of your country.

This does NOT play anything or touch your account beyond reading it. It just
produces a report so you know, before building anything else, what fraction
of your library is actually usable in a custom player.


SETUP (one-time)
-----------------
1. Install dependencies:

     pip install ytmusicapi requests --break-system-packages

   (requests usually comes in already as a dependency of ytmusicapi)

2. Authenticate ytmusicapi against YOUR YouTube Music account.
   Easiest path for a personal/local tool — no Google Cloud project needed:

     ytmusicapi browser

   This walks you through copying request headers from your browser's
   devtools while logged into https://music.youtube.com (Network tab, filter
   for a "/browse" request, copy request headers). Paste them when prompted.
   It writes a `browser.json` file in the current folder. These credentials
   stay valid for roughly 2 years unless you log out of that browser session.

   (There's also an OAuth method, but as of late 2024 it requires you to
   register your own Google Cloud OAuth client and has been flakier in
   practice — browser auth is simpler for solo, local use.)

3. Get a free YouTube Data API v3 key. This is SEPARATE from the ytmusicapi
   login above, and is just a read-only key for public video metadata:

     - Go to https://console.cloud.google.com/
     - Create (or pick) a project
     - APIs & Services -> Library -> enable "YouTube Data API v3"
     - APIs & Services -> Credentials -> Create Credentials -> API key
     - Create a plain text file named `youtube_api_key.txt` in this same
       folder, and paste just the key into it, nothing else (no quotes).
       The script reads it from there automatically.

   The free daily quota (10,000 units) is far more than enough — this script
   uses ~1 unit per 50 tracks checked.

4. Set YOUR_COUNTRY below to your two-letter region code (e.g. "CA" for
   Canada, "US" for the US). This is used to check region restrictions.

5. Run it:

     python3 check_embeddability.py

It prints a summary to the console and writes a full per-track CSV report.
"""

import csv
import os
import sys
import time

import requests
from ytmusicapi import YTMusic

# ---------------------------------------------------------------------------
# CONFIG — edit these
# ---------------------------------------------------------------------------
def load_api_key() -> str:
    """Reads the YouTube Data API key from youtube_api_key.txt, falling
    back to the YOUTUBE_API_KEY environment variable if that file isn't
    there."""
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    return os.environ.get("YOUTUBE_API_KEY", "")


AUTH_FILE = "browser.json"  # output of `ytmusicapi browser`
API_KEY_FILE = "youtube_api_key.txt"  # plain text file containing just the key
YOUTUBE_API_KEY = load_api_key()
YOUR_COUNTRY = "CA"  # ISO 3166-1 alpha-2 country code
OUTPUT_CSV = "embeddability_report.csv"
BATCH_SIZE = 50  # max video IDs per YouTube Data API v3 videos.list call
REQUEST_DELAY = 0.2  # be polite between batches, not required but nice


def get_library_tracks(yt: YTMusic) -> dict[str, dict]:
    """Pull saved library songs + liked songs, deduped by videoId."""
    print("Fetching your YouTube Music library...")

    by_id: dict[str, dict] = {}

    library_songs = yt.get_library_songs(limit=None)
    print(f"  {len(library_songs)} songs in your library")

    liked = yt.get_liked_songs(limit=None)
    liked_songs = liked.get("tracks", [])
    print(f"  {len(liked_songs)} liked songs")

    for song in library_songs + liked_songs:
        video_id = song.get("videoId")
        if not video_id:
            continue
        artist_names = ", ".join(
            a["name"] for a in (song.get("artists") or []) if a.get("name")
        )
        by_id[video_id] = {
            "videoId": video_id,
            "title": song.get("title") or "Unknown title",
            "artist": artist_names,
        }

    print(f"Total unique tracks to check: {len(by_id)}")
    return by_id


def chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def check_batch(video_ids: list[str]) -> list[dict]:
    """Call YouTube Data API v3 videos.list for up to 50 IDs at once."""
    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={
            "part": "status,contentDetails",
            "id": ",".join(video_ids),
            "key": YOUTUBE_API_KEY,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"YouTube Data API error {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json().get("items", [])


def is_region_blocked(content_details: dict, country: str) -> bool:
    region = content_details.get("regionRestriction")
    if not region:
        return False
    allowed = region.get("allowed")
    blocked = region.get("blocked")
    if allowed is not None:
        return country not in allowed
    if blocked is not None:
        return country in blocked
    return False


def is_age_restricted(content_details: dict) -> bool:
    """Age-restricted videos can't be embedded ANYWHERE, regardless of the
    owner's 'allow embedding' setting (status.embeddable can still say
    True). This is a separate, YouTube-enforced restriction, flagged here
    instead via contentRating.ytRating == 'ytAgeRestricted'."""
    rating = content_details.get("contentRating", {})
    return rating.get("ytRating") == "ytAgeRestricted"


def main():
    if not YOUTUBE_API_KEY:
        sys.exit(
            f"No YouTube Data API key found. Create a file named "
            f"{API_KEY_FILE} in this folder containing just your key, or "
            "set YOUTUBE_API_KEY as an environment variable. See the setup "
            "instructions at the top of this file."
        )

    if not os.path.exists(AUTH_FILE):
        sys.exit(
            f"Couldn't find {AUTH_FILE}. Run `ytmusicapi browser` first to "
            "create it (see setup instructions at the top of this file)."
        )

    yt = YTMusic(AUTH_FILE)
    by_id = get_library_tracks(yt)
    all_ids = list(by_id.keys())

    results = []
    found_ids = set()

    total_batches = (len(all_ids) + BATCH_SIZE - 1) // BATCH_SIZE
    print(
        f"\nChecking embeddability via YouTube Data API "
        f"({len(all_ids)} tracks, {total_batches} batches of {BATCH_SIZE})..."
    )

    for batch_num, batch in enumerate(chunked(all_ids, BATCH_SIZE), start=1):
        items = check_batch(batch)
        for item in items:
            vid = item["id"]
            found_ids.add(vid)
            status = item.get("status", {})
            content = item.get("contentDetails", {})
            embeddable_raw = status.get("embeddable")  # None if the field is just absent
            embeddable_unknown = embeddable_raw is None
            embeddable = True if embeddable_unknown else embeddable_raw
            region_blocked = is_region_blocked(content, YOUR_COUNTRY)
            age_restricted = is_age_restricted(content)
            track = by_id[vid]
            results.append(
                {
                    **track,
                    "embeddable": embeddable,
                    "embeddable_unknown": embeddable_unknown,
                    "region_blocked": region_blocked,
                    "age_restricted": age_restricted,
                    "playable": embeddable and not region_blocked and not age_restricted,
                    "note": "embeddable field missing from API response" if embeddable_unknown else "",
                }
            )
        print(f"  batch {batch_num}/{total_batches} checked")
        time.sleep(REQUEST_DELAY)

    # IDs ytmusicapi knew about but the Data API didn't return at all are
    # usually deleted, private, or otherwise gone.
    missing_ids = set(all_ids) - found_ids
    for vid in missing_ids:
        track = by_id[vid]
        results.append(
            {
                **track,
                "embeddable": False,
                "embeddable_unknown": False,
                "region_blocked": False,
                "age_restricted": False,
                "playable": False,
                "note": "not returned by API (likely removed/private)",
            }
        )

    # ---------------- summary ----------------
    total = len(results)
    playable = sum(1 for r in results if r["playable"])
    not_embeddable = sum(1 for r in results if not r["embeddable"])
    embeddable_unknown = sum(1 for r in results if r["embeddable_unknown"])
    age_restricted = sum(1 for r in results if r["age_restricted"])
    region_blocked = sum(1 for r in results if r["region_blocked"])
    missing = len(missing_ids)

    print("\n=== Summary ===")
    print(f"Total tracks checked:        {total}")
    if total:
        print(f"Playable in an embed:        {playable} ({playable / total:.1%})")
    print(f"Owner disabled embedding:    {not_embeddable}")
    print(f"  (of which, field was missing — unverified, assumed OK): {embeddable_unknown}")
    print(f"Age-restricted (no embeds):  {age_restricted}")
    print(f"Region-blocked in {YOUR_COUNTRY}:          {region_blocked}")
    print(f"Not found (likely removed):  {missing}")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "videoId",
                "title",
                "artist",
                "embeddable",
                "embeddable_unknown",
                "region_blocked",
                "age_restricted",
                "playable",
                "note",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\nFull per-track report written to {OUTPUT_CSV}")
    print("(unplayable/blocked tracks are easiest to find by sorting that "
          "CSV on the 'playable' column)")


if __name__ == "__main__":
    main()