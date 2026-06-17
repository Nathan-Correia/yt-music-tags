# ytmusicapi Response Reference

Real captured response samples for the ytmusicapi calls this project uses, pulled directly from a test run against a real account. Since this is an unofficial API with no published response schema, this doc exists so the actual shape is documented somewhere concrete instead of being re-discovered by trial and error.

## `get_library_songs`

Returns a plain list. Sample item:

```json
{
  "videoId": "GwSSrwryxN0",
  "title": "Impostor Syndrome",
  "artists": [
    { "name": "Sidney Gish", "id": "UC055vqwIBYTLhujKQMdjhCg" }
  ],
  "album": { "name": "No Dogs Allowed", "id": "MPREb_AwaBe5vs5Wa" },
  "likeStatus": "LIKE",
  "inLibrary": true,
  "pinnedToListenAgain": false,
  "feedbackTokens": { "add": "<opaque token, not used>", "remove": "<opaque token, not used>" },
  "listenAgainFeedbackTokens": { "pin": "<opaque token, not used>", "unpin": "<opaque token, not used>" },
  "thumbnails": [
    { "url": "https://...", "width": 60, "height": 60 },
    { "url": "https://...", "width": 120, "height": 120 }
  ],
  "isAvailable": true,
  "isExplicit": true,
  "videoType": "MUSIC_VIDEO_TYPE_ATV",
  "views": null,
  "communityVoteStatus": null,
  "duration": "4:55",
  "duration_seconds": 295,
  "creditsBrowseId": "MPTCGwSSrwryxN0"
}
```

Mapping to the `songs` table: `videoId`→`video_id`, `title`→`title`, `artists[].name` (joined into a JSON list of names)→`artists`, `album.name`→`album`, `duration_seconds`→`duration_seconds` (already an int, no need to parse the `"4:55"` string form), `isExplicit`→`is_explicit`, `videoType`→`video_type`. Everything else in this payload (`likeStatus`, `inLibrary` — redundant, we set this flag ourselves rather than trusting it — `pinnedToListenAgain`, the feedback tokens, `thumbnails`, `isAvailable`, `views`, `communityVoteStatus`, `duration`, `creditsBrowseId`) is unused and can be ignored.

## `get_liked_songs`

Confirmed: returns a dict, not a list. Top-level keys observed: `owned`, `id`, `privacy`, `description`, `views`, `duration`, `trackCount`, `title`, `thumbnails`, `author`, `year`, `related`, `tracks`, `duration_seconds`. The actual song list lives under `tracks`, and each entry has the exact same shape as a `get_library_songs` item above (same fields, same `feedbackTokens`/`thumbnails`/etc. noise to ignore).

## `get_song` (`videoDetails` only)

The full `get_song()` response has more top-level sections, but `videoDetails` is the only one this project needs. Sample:

```json
{
  "videoId": "GwSSrwryxN0",
  "title": "Impostor Syndrome",
  "lengthSeconds": "294",
  "channelId": "UC055vqwIBYTLhujKQMdjhCg",
  "isOwnerViewing": false,
  "isCrawlable": true,
  "thumbnail": { "thumbnails": [ { "url": "https://...", "width": 544, "height": 544 } ] },
  "allowRatings": true,
  "viewCount": "20606640",
  "author": "Sidney Gish",
  "isPrivate": false,
  "isUnpluggedCorpus": false,
  "musicVideoType": "MUSIC_VIDEO_TYPE_ATV",
  "isLiveContent": false,
  "isTvfilmVideo": false
}
```

Confirms `viewCount` arrives as a **string** (`"20606640"`), matching the documented cast-to-int requirement. `lengthSeconds` is also a string, and a slightly different value (294) than `duration_seconds` from the library/liked sync (295) — not a concern since `duration_seconds` already comes from those calls and `lengthSeconds` isn't used here at all.

## `create_playlist` + the indexing-delay retry

`create_playlist` returned the new playlist's id directly as a string: `PL6YTI1OPBkkR62I3f4lQtDjO3cb9gFDQY`.

Calling `get_playlist` immediately afterward failed on the first attempt with this real error text:

```
Unable to find 'contents' using path ['contents', 'twoColumnBrowseResultsRenderer', 'tabs', 0, 'tabRenderer', 'content', 'sectionListRenderer', 'contents', 0] on {...}, exception: 'contents'
```

This confirms the documented retry gotcha and gives the literal message text, in case it's ever worth matching against this specific failure rather than retrying blindly on any exception. After a 2-second wait, the second attempt succeeded.

## `get_playlist` (tracks)

Sample track from the freshly-created test playlist:

```json
{
  "videoId": "GwSSrwryxN0",
  "title": "Impostor Syndrome",
  "artists": [ { "name": "Sidney Gish", "id": "UC055vqwIBYTLhujKQMdjhCg" } ],
  "album": { "name": "No Dogs Allowed", "id": "MPREb_AwaBe5vs5Wa" },
  "isAvailable": true,
  "isExplicit": true,
  "videoType": "MUSIC_VIDEO_TYPE_ATV",
  "duration": "4:55",
  "duration_seconds": 295,
  "setVideoId": "56B44F6D10557CC6",
  "creditsBrowseId": "MPTCGwSSrwryxN0"
}
```

Same shape as a library/liked song entry, plus one field only present here: `setVideoId`. Confirms this is the only place it's available, and it's what `remove_playlist_items` needs alongside `videoId`.

## `remove_playlist_items`

Returned a value of `STATUS_SUCCEEDED` in this test — there is a usable success signal here, unlike `delete_playlist` below. The test script only printed the extracted value rather than the raw dict it came from, so the exact key/path it lives under wasn't captured — worth a quick look at the raw response if you want to branch on it explicitly rather than just checking for an exception.

## `delete_playlist`

Real captured return value, in full:

```json
{
  "responseContext": {
    "serviceTrackingParams": [
      { "service": "CSI", "params": [{ "key": "c", "value": "WEB_REMIX" }, { "key": "cver", "value": "1.20260617.01.00" }] },
      { "service": "GFEEDBACK", "params": [{ "key": "logged_in", "value": "1" }] },
      { "service": "ECATCHER", "params": [{ "key": "client.version", "value": "1.20000101" }, { "key": "client.name", "value": "WEB_REMIX" }] }
    ],
    "consistencyTokenJar": { "encryptedTokenJarContents": "<opaque>", "expirationSeconds": "600" },
    "responseId": "IhMI_6zpze6NlQMVeEtMCB2F6R4m"
  },
  "command": {
    "commandExecutorCommand": {
      "commands": [
        { "handlePlaylistDeletionCommand": { "playlistId": "PL6YTI1OPBkkR62I3f4lQtDjO3cb9gFDQY" } },
        { "removeFromGuideSectionAction": { "handlerData": "GUIDE_ACTION_REMOVE_FROM_PLAYLISTS", "guideEntryId": "PL6YTI1OPBkkR62I3f4lQtDjO3cb9gFDQY" } }
      ]
    }
  }
}
```

No status or success field anywhere in this payload — confirms the existing guidance to treat "no exception raised" as the success signal rather than trying to parse this response.

## `get_history`

Confirmed: 199 entries returned in this pull, matching the documented ~199-200 fixed-batch behavior. Sample entry:

```json
{
  "videoId": "Xt_F4J4O-xo",
  "title": "Machu Picchu",
  "artists": [ { "name": "The Strokes", "id": "UC8N13xhRG78YQK7Ppc4Ytrg" } ],
  "album": { "name": "Angles", "id": "MPREb_ZB6767Lns0g" },
  "likeStatus": "LIKE",
  "inLibrary": true,
  "pinnedToListenAgain": false,
  "feedbackTokens": { "add": "<opaque, not used>", "remove": "<opaque, not used>" },
  "feedbackToken": "<opaque, not used>",
  "listenAgainFeedbackTokens": { "pin": "<opaque, not used>", "unpin": "<opaque, not used>" },
  "thumbnails": [ { "url": "https://...", "width": 60, "height": 60 }, { "url": "https://...", "width": 120, "height": 120 } ],
  "isAvailable": true,
  "isExplicit": false,
  "videoType": "MUSIC_VIDEO_TYPE_ATV",
  "views": null,
  "communityVoteStatus": null,
  "duration": "3:30",
  "duration_seconds": 210,
  "creditsBrowseId": "MPTCXt_F4J4O-xo",
  "played": "Today"
}
```

Same shape as a library song entry, plus two history-specific fields: `played` (the relative label this project converts into an absolute date) and a singular `feedbackToken`, distinct from the plural `feedbackTokens` seen elsewhere — this one is what `remove_history_items` would need, not used by this project.

A full scan across all 199 entries confirmed `played` is the only date/time-related key anywhere in the payload — there's genuinely no absolute timestamp to fall back on, exactly as documented.

On the dedup claim specifically: this pull came back with 199 unique `videoId`s and zero duplicates, which is *consistent* with "deduplicated to one entry per song" but doesn't fully prove it — it's equally explained by simply not having replayed anything recently. Worth treating as still-unconfirmed rather than settled until a pull happens to catch an actual repeat play.

## Not yet captured

`get_library_playlists` (used as the fallback lookup when `yt_playlist_id` isn't known yet) and `add_playlist_items` (used to refill a playlist during refresh) haven't been captured in a test pass yet. Both are used in the Query evaluation + playlist refresh workflow, so worth a quick capture before that part gets implemented for real.
