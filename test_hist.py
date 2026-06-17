"""
test_history.py

Diagnostic script to figure out what ytmusicapi's get_history() actually gives us:
- how many entries it returns (vs. what you see scrolling the History page in the app)
- whether entries have any date/timestamp-like field
- whether the same song (videoId) ever appears more than once

Usage:
    1. Set AUTH_FILE below to whatever auth file you're already using with ytmusicapi
       (e.g. "oauth.json" or "browser.json").
    2. Run: python test_history.py
    3. Read the printed summary, and check history_dump.json for the full raw data.

Bonus test: play the same song twice in the app (skip to end, replay it), then
re-run this script and look at the "duplicate" section — that's the cleanest way
to see whether get_history() collapses repeats or shows them separately.
"""

import json
from collections import Counter

from ytmusicapi import YTMusic

AUTH_FILE = "browser.json"  # <-- change this if your auth file has a different name


def main():
    yt = YTMusic(AUTH_FILE)

    print("Fetching history...")
    history = yt.get_history()

    print(f"\nTotal entries returned: {len(history)}")

    if not history:
        print("No history returned — check your auth file / account.")
        return

    # Show the raw shape of one entry so we can see exactly what fields exist
    print("\n--- Sample entry (first item) ---")
    print(json.dumps(history[0], indent=2, default=str))

    # Collect every key seen across all entries (some fields might not be on every item)
    all_keys = set()
    for item in history:
        all_keys.update(item.keys())
    print(f"\nAll keys seen across entries: {sorted(all_keys)}")

    # Heuristic: look for anything that smells like a date/time field
    time_like_keys = [
        k for k in all_keys
        if any(s in k.lower() for s in ["time", "date", "play", "added", "when"])
    ]
    if time_like_keys:
        print(f"\nPossible date/time-related keys found: {time_like_keys}")
        for k in time_like_keys:
            sample_values = [item.get(k) for item in history[:5]]
            print(f"  {k}: {sample_values}")
    else:
        print("\nNo obvious date/time field found on entries — "
              "history may not expose exact timestamps, just order.")

    # Check for duplicate videoIds (same song appearing more than once)
    video_ids = [item.get("videoId") for item in history if item.get("videoId")]
    counts = Counter(video_ids)
    duplicates = {vid: c for vid, c in counts.items() if c > 1}

    print(f"\nUnique videoIds: {len(counts)}")
    print(f"VideoIds appearing more than once: {len(duplicates)}")

    if duplicates:
        print("\n--- Duplicate examples ---")
        for vid, c in list(duplicates.items())[:10]:
            title = next(
                (item.get("title") for item in history if item.get("videoId") == vid),
                "?",
            )
            print(f"  '{title}' ({vid}): appears {c} times")
    else:
        print("No duplicates found in this pull — either you haven't replayed "
              "anything recently, or get_history() collapses repeats to the "
              "most recent play.")

    # Dump the full raw response so you can manually scroll/inspect it
    with open("history_dump.json", "w") as f:
        json.dump(history, f, indent=2, default=str)
    print("\nFull raw history saved to history_dump.json for manual inspection.")


if __name__ == "__main__":
    main()