#!/usr/bin/env python3
"""
Local library server
=====================

Tiny local backend that reads your YouTube Music library via `ytmusicapi`
and serves it as JSON, so the frontend (index.html/app.js) has something to
fetch and display. This never touches the official YouTube Data API, that
part isn't needed just to list + play your own library.

SETUP (one-time, reuses the browser.json from the embeddability checker)
--------------------------------------------------------------------
  pip install flask ytmusicapi --break-system-packages

  If you don't already have browser.json from before, run:
    ytmusicapi browser
  and paste the request headers as described there.

RUN
---
  python3 server.py

Then open http://localhost:5001 in your browser — that's it, this same
server hosts the page AND the API:
  GET  /              -> the app (index.html)
  GET  /api/library    -> list of {videoId, title, artist, album, thumbnail}
  POST /api/refresh    -> clears the cache and re-fetches from YouTube Music
"""

import os
import sys

from flask import Flask, jsonify, send_from_directory
from ytmusicapi import YTMusic

AUTH_FILE = "browser.json"
APP_DIR = os.path.dirname(os.path.abspath(__file__))

if not os.path.exists(AUTH_FILE):
    sys.exit(
        f"Couldn't find {AUTH_FILE}. Run `ytmusicapi browser` first "
        "(see the comment block at the top of this file)."
    )

app = Flask(__name__)
# No flask-cors here on purpose: everything is same-origin now (the page is
# served by this same server), and this folder also holds browser.json /
# youtube_api_key.txt. Wide-open CORS plus serving the whole directory would
# let any website you visit in another tab read those over localhost. The
# routes below serve only the three specific frontend files, nothing else.


@app.route("/")
def index():
    return send_from_directory(APP_DIR, "index.html")


@app.route("/style.css")
def style():
    return send_from_directory(APP_DIR, "style.css")


@app.route("/app.js")
def app_js():
    return send_from_directory(APP_DIR, "app.js")


yt = YTMusic(AUTH_FILE)
_cache = None


def load_library():
    global _cache
    if _cache is not None:
        return _cache

    by_id = {}

    library_songs = yt.get_library_songs(limit=None)
    liked_songs = yt.get_liked_songs(limit=None).get("tracks", [])

    for song in library_songs + liked_songs:
        video_id = song.get("videoId")
        if not video_id:
            continue

        artists = ", ".join(
            a["name"] for a in (song.get("artists") or []) if a.get("name")
        )
        album = song.get("album")
        album_name = album.get("name") if isinstance(album, dict) else None
        thumbnails = song.get("thumbnails") or []
        thumbnail = thumbnails[0]["url"] if thumbnails else None

        by_id[video_id] = {
            "videoId": video_id,
            "title": song.get("title") or "Unknown title",
            "artist": artists,
            "album": album_name,
            "thumbnail": thumbnail,
        }

    _cache = list(by_id.values())
    return _cache


@app.route("/api/library")
def api_library():
    return jsonify(load_library())


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    global _cache
    _cache = None
    return jsonify(load_library())


if __name__ == "__main__":
    print("Loading your library once at startup (this can take a moment)...")
    print(f"  {len(load_library())} unique tracks loaded")
    print("Open http://localhost:5001 in your browser")
    app.run(port=5001, debug=True)