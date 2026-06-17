"""
inspect_endpoints.py

Prints the signature and docstring for the ytmusicapi methods most relevant
to this project (pulling your library for tagging, and creating/refreshing
playlists), so we can see exactly what each one expects and returns before
building real logic around them.

Note: this uses inspect.signature()/inspect.getdoc() instead of calling
help() directly. help() can sometimes try to launch a pager (especially on
Windows), which would make the script hang waiting for input instead of
just printing and exiting. This gives the same info without that risk.

Usage:
    1. Set AUTH_FILE below to whatever auth file you're using.
    2. Run: python inspect_endpoints.py
    3. Copy the full output and paste it back.

Feel free to add/remove names in METHODS_TO_INSPECT below if you want to
check other endpoints later.
"""

import inspect

from ytmusicapi import YTMusic

AUTH_FILE = "browser.json"  # <-- change this if your auth file has a different name

METHODS_TO_INSPECT = [
    "get_library_songs",
    "get_liked_songs",
    "get_library_playlists",
    "get_song",
    "search",
    "get_playlist",
    "create_playlist",
    "edit_playlist",
    "add_playlist_items",
    "remove_playlist_items",
]


def main():
    yt = YTMusic(AUTH_FILE)

    for name in METHODS_TO_INSPECT:
        method = getattr(yt, name, None)

        print("=" * 80)
        print(name)
        print("=" * 80)

        if method is None:
            print(f"(no such method: {name})\n")
            continue

        try:
            sig = inspect.signature(method)
            print(f"{name}{sig}")
        except (TypeError, ValueError) as e:
            print(f"(could not get signature: {e})")

        doc = inspect.getdoc(method)
        print()
        print(doc if doc else "(no docstring)")
        print()


if __name__ == "__main__":
    main()