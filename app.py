import threading

from flask import Flask, jsonify, render_template, request

import db
import ytmusic

app = Flask(__name__)
db.init_db()

# ---------------------------------------------------------------------------
# Background enrichment state
# ---------------------------------------------------------------------------
_enrich_lock = threading.Lock()
_enrich = {"running": False, "total": 0, "done": 0, "stop": False}
_enrich_thread = None


def _run_enrichment():
    video_ids = db.get_songs_missing_view_count()
    with _enrich_lock:
        _enrich.update(total=len(video_ids), done=0, running=True, stop=False)

    def on_progress():
        with _enrich_lock:
            _enrich["done"] += 1

    def should_stop():
        with _enrich_lock:
            return _enrich["stop"]

    try:
        ytmusic.enrich_batch(video_ids, on_progress, should_stop)
    finally:
        with _enrich_lock:
            _enrich["running"] = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sync", methods=["POST"])
def sync():
    try:
        count = ytmusic.sync()
        return jsonify({"ok": True, "count": count})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/enrich/start", methods=["POST"])
def enrich_start():
    global _enrich_thread
    with _enrich_lock:
        if _enrich["running"]:
            return jsonify({"ok": False, "error": "Already running"}), 400
    _enrich_thread = threading.Thread(target=_run_enrichment, daemon=True)
    _enrich_thread.start()
    return jsonify({"ok": True})


@app.route("/api/enrich/stop", methods=["POST"])
def enrich_stop():
    with _enrich_lock:
        _enrich["stop"] = True
    return jsonify({"ok": True})


@app.route("/api/enrich/status")
def enrich_status():
    with _enrich_lock:
        return jsonify(dict(_enrich))


@app.route("/api/songs")
def songs():
    expression = request.args.get("q", "").strip() or None
    try:
        rows = db.query_songs(expression)
        return jsonify({"ok": True, "songs": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/songs/bulk", methods=["POST"])
def songs_bulk():
    data = request.get_json(force=True)
    video_ids = data.get("video_ids") or []
    attr = data.get("attr")
    value = data.get("value")
    if not video_ids or not attr:
        return jsonify({"ok": False, "error": "Missing video_ids or attr"}), 400
    try:
        db.bulk_update_attr(video_ids, attr, value)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/songs/<video_id>", methods=["PATCH"])
def song_update(video_id):
    data = request.get_json(force=True)
    attr = data.get("attr")
    value = data.get("value")
    if not attr:
        return jsonify({"ok": False, "error": "Missing attr"}), 400
    try:
        db.update_song_attr(video_id, attr, value)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/attributes")
def attributes():
    return jsonify(db.get_attributes())


@app.route("/api/playlist", methods=["POST"])
def playlist():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    expression = (data.get("expression") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Playlist name required"}), 400
    try:
        playlist_id, action = ytmusic.create_or_refresh_playlist(name, expression)
        return jsonify({"ok": True, "playlist_id": playlist_id, "action": action})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
