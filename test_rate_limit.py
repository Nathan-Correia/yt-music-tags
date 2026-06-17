#!/usr/bin/env python3
"""
Empirical probe for ytmusicapi get_song() rate limits.

ytmusicapi has no published numeric rate limit for browse-type calls like
get_song() -- the only officially documented limit is on playlist
*creation* (a clean 429 "RESOURCE_EXHAUSTED" with a readable message).
For everything else, including get_song(), the only way to know a real
number for your own account is to test it directly.

Worth knowing before reading results: when ytmusicapi DOES get rate
limited on other endpoints, it's been reported to surface as a confusing
KeyError (e.g. a missing 'videoDetails' key) rather than a clean 429
message, because the library expects a normal response shape and the
error response doesn't have it. Because of that, this script treats ANY
exception as a stop condition rather than trying to guess whether it
"looks like" a rate limit from the message text -- the safest read on an
error here is just "something went wrong with this request."

Run this locally where ytmusicapi is already installed and browser.json
is already configured. It needs real network access to YouTube Music's
API, which isn't available from a sandboxed assistant environment.

Usage:
    python test_rate_limit.py --auth browser.json --count 300 --delay 0.3
    python test_rate_limit.py --auth browser.json --count 500 --delay 0

Try a few different --delay values (e.g. 0, 0.2, 0.5, 1.0) across separate
runs to find where it starts failing, then use a value comfortably above
that as the real throttle for the metadata enrichment pass.
"""

import argparse
import sys
import time

from ytmusicapi import YTMusic


def gather_video_ids(yt, count):
    """Pull real video IDs from the user's own library/liked songs to test against."""
    ids = []
    try:
        liked = yt.get_liked_songs(limit=count)
        ids += [t["videoId"] for t in liked.get("tracks", []) if t.get("videoId")]
    except Exception as e:
        print(f"  (couldn't fetch liked songs: {e})")

    if len(ids) < count:
        try:
            library = yt.get_library_songs(limit=count)
            ids += [t["videoId"] for t in library if t.get("videoId")]
        except Exception as e:
            print(f"  (couldn't fetch library songs: {e})")

    seen, deduped = set(), []
    for vid in ids:
        if vid not in seen:
            seen.add(vid)
            deduped.append(vid)
    return deduped[:count]


def main():
    parser = argparse.ArgumentParser(description="Probe ytmusicapi get_song() rate limits empirically.")
    parser.add_argument("--auth", default="browser.json", help="Path to browser.json (default: browser.json)")
    parser.add_argument("--count", type=int, default=300, help="How many get_song() calls to attempt")
    parser.add_argument("--delay", type=float, default=0.3, help="Seconds to sleep between calls")
    args = parser.parse_args()

    print(f"Authenticating with {args.auth} ...")
    yt = YTMusic(args.auth)

    print(f"Gathering up to {args.count} real video IDs from your library/liked songs ...")
    video_ids = gather_video_ids(yt, args.count)
    if not video_ids:
        print("Couldn't find any video IDs to test with -- is your library/liked songs empty?")
        sys.exit(1)
    print(f"Got {len(video_ids)} video IDs. Probing at {args.delay}s delay between calls.\n")

    success = 0
    start = time.monotonic()

    try:
        for i, vid in enumerate(video_ids, start=1):
            call_start = time.monotonic()
            try:
                yt.get_song(vid)
                success += 1
                print(f"[{i}/{len(video_ids)}] ok  ({time.monotonic() - call_start:.2f}s)")
            except Exception as e:
                print(f"\n[{i}/{len(video_ids)}] FAILED ({time.monotonic() - call_start:.2f}s)")
                print(f"  exception type: {type(e).__name__}")
                print(f"  message: {e}")
                print("\nStopping here -- treating any exception as a potential rate-limit signal.")
                break
            time.sleep(args.delay)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")

    elapsed = time.monotonic() - start
    print("\n--- Summary ---")
    print(f"Successful calls before stopping: {success}/{len(video_ids)} attempted")
    if elapsed > 0:
        print(f"Total time: {elapsed:.1f}s ({success / elapsed:.2f} calls/sec sustained)")


if __name__ == "__main__":
    main()