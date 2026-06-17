const ERROR_MESSAGES = {
  2: "Invalid video reference.",
  5: "Can't play this in an HTML5 player.",
  100: "This track was removed or made private.",
  101: "101: The rights holder doesn't allow this track in embedded players.",
  150: "150: The rights holder doesn't allow this track in embedded players.",
  153: "Embed blocked — missing referrer info.",
};

// ---- DOM refs ----
const searchInput = document.getElementById("search");
const countEl = document.getElementById("count");
const refreshBtn = document.getElementById("refresh-btn");
const stateMsg = document.getElementById("state-msg");
const listEl = document.getElementById("list");
const dockTitle = document.getElementById("dock-title");
const dockArtist = document.getElementById("dock-artist");
const dockError = document.getElementById("dock-error");
const dockEmpty = document.getElementById("dock-empty");
const playBtn = document.getElementById("play-btn");

// ---- state ----
let songs = [];
let query = "";
let currentTrack = null;
let isPlaying = false;
let player = null;
let playerReady = false;

// ---- library loading ----
function setStateMsg(text, isError) {
  if (!text) {
    stateMsg.style.display = "none";
    return;
  }
  stateMsg.style.display = "block";
  stateMsg.textContent = text;
  stateMsg.className = "state-msg" + (isError ? " error" : "");
}

function fetchLibrary() {
  setStateMsg("Loading your library…", false);
  countEl.textContent = "loading…";
  fetch("/api/library")
    .then((r) => {
      if (!r.ok) throw new Error(`Server responded ${r.status}`);
      return r.json();
    })
    .then((data) => {
      songs = data;
      renderList();
    })
    .catch((err) => {
      setStateMsg(
        `Couldn't reach the local server (${err.message}). Is server.py running?`,
        true
      );
      countEl.textContent = "—";
    });
}

function refreshLibrary() {
  refreshBtn.disabled = true;
  setStateMsg("Refreshing…", false);
  fetch("/api/refresh", { method: "POST" })
    .then((r) => r.json())
    .then((data) => {
      songs = data;
      renderList();
    })
    .catch((err) => setStateMsg(err.message, true))
    .finally(() => {
      refreshBtn.disabled = false;
    });
}

// ---- rendering ----
function getFiltered() {
  const q = query.trim().toLowerCase();
  if (!q) return songs;
  return songs.filter(
    (s) =>
      s.title.toLowerCase().includes(q) ||
      (s.artist || "").toLowerCase().includes(q)
  );
}

function renderList() {
  const filtered = getFiltered();
  countEl.textContent = `${filtered.length} / ${songs.length}`;

  listEl.innerHTML = "";

  if (filtered.length === 0) {
    setStateMsg(
      songs.length === 0 ? "No tracks in your library yet." : `No tracks match "${query}".`,
      false
    );
    return;
  }
  setStateMsg(null);

  for (const song of filtered) {
    listEl.appendChild(createRow(song));
  }
}

function createRow(song) {
  const row = document.createElement("button");
  row.className =
    "row" + (currentTrack && currentTrack.videoId === song.videoId ? " active" : "");
  row.addEventListener("click", () => playSong(song));

  if (song.thumbnail) {
    const img = document.createElement("img");
    img.className = "thumb";
    img.src = song.thumbnail;
    img.alt = "";
    row.appendChild(img);
  } else {
    const placeholder = document.createElement("div");
    placeholder.className = "thumb placeholder";
    placeholder.textContent = "♪";
    row.appendChild(placeholder);
  }

  const textWrap = document.createElement("div");
  textWrap.className = "row-text";

  const titleEl = document.createElement("div");
  titleEl.className = "row-title";
  titleEl.textContent = song.title;

  const artistEl = document.createElement("div");
  artistEl.className = "row-artist";
  artistEl.textContent = song.artist || "";

  textWrap.appendChild(titleEl);
  textWrap.appendChild(artistEl);
  row.appendChild(textWrap);

  return row;
}

// ---- YouTube IFrame Player ----
function loadYouTubeApi() {
  if (window.YT && window.YT.Player) {
    createPlayer();
    return;
  }
  window.onYouTubeIframeAPIReady = createPlayer;
  const tag = document.createElement("script");
  tag.src = "https://www.youtube.com/iframe_api";
  document.body.appendChild(tag);
}

function createPlayer() {
  player = new YT.Player("yt-mount", {
    height: "64",
    width: "64",
    playerVars: { playsinline: 1, origin: window.location.origin },
    events: {
      onReady: () => {
        playerReady = true;
        updateDockControls();
      },
      onStateChange: (e) => {
        isPlaying = e.data === YT.PlayerState.PLAYING;
        updateDockControls();
      },
      onError: (e) => {
        isPlaying = false;
        dockError.textContent = ERROR_MESSAGES[e.data] || `Playback error (code ${e.data})`;
        updateDockControls();
      },
    },
  });
}

// ---- playback ----
function playSong(song) {
  currentTrack = song;
  dockError.textContent = "";
  dockEmpty.style.display = "none";
  dockTitle.textContent = song.title;
  dockArtist.textContent = song.artist || "";

  if (player && player.loadVideoById) {
    player.loadVideoById(song.videoId);
    player.playVideo();
  }

  renderList();
  updateDockControls();
}

function togglePlayPause() {
  if (!player || !currentTrack) return;
  if (isPlaying) player.pauseVideo();
  else player.playVideo();
}

function updateDockControls() {
  playBtn.disabled = !currentTrack || !playerReady;
  playBtn.textContent = isPlaying ? "❚❚" : "▶";
}

// ---- wire up ----
searchInput.addEventListener("input", (e) => {
  query = e.target.value;
  renderList();
});
refreshBtn.addEventListener("click", refreshLibrary);
playBtn.addEventListener("click", togglePlayPause);

fetchLibrary();
loadYouTubeApi();