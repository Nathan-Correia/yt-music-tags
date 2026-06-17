"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let songs = [];
let attributes = [];      // [{name, value_type, min_value, max_value, allowed_values, default_value}]
let attrByName = {};      // name -> attribute meta
let selectedIds = new Set();
let enrichPollTimer = null;

// ---------------------------------------------------------------------------
// Core columns shown before attribute columns
// ---------------------------------------------------------------------------
const CORE_COLS = [
  { key: "title",            label: "Title",       width: 200 },
  { key: "artists",          label: "Artists",     width: 160, format: fmtArtists },
  { key: "album",            label: "Album",       width: 150 },
  { key: "duration_seconds", label: "Dur",         width: 55,  format: fmtDuration },
  { key: "is_explicit",      label: "E",           width: 24,  format: v => v ? "E" : "" },
  { key: "view_count",       label: "Views",       width: 80,  format: fmtViews },
  { key: "in_library",       label: "Lib",         width: 30,  format: v => v ? "✓" : "" },
  { key: "liked",            label: "♥",           width: 24,  format: v => v ? "♥" : "" },
  { key: "last_played",      label: "Last Played", width: 95 },
];

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------
function fmtArtists(v) {
  try { return JSON.parse(v).join(", "); } catch { return v || ""; }
}

function fmtDuration(v) {
  if (v == null) return "";
  const m = Math.floor(v / 60);
  const s = String(v % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function fmtViews(v) {
  return v != null ? Number(v).toLocaleString() : "";
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  return res.json();
}

// ---------------------------------------------------------------------------
// Attribute list
// ---------------------------------------------------------------------------
async function loadAttributes() {
  attributes = await api("GET", "/api/attributes");
  attrByName = Object.fromEntries(attributes.map(a => [a.name, a]));
  populateBulkSelect();
}

function populateBulkSelect() {
  const sel = document.getElementById("bulk-attr");
  sel.innerHTML = attributes
    .map(a => `<option value="${esc(a.name)}">${esc(a.name)}</option>`)
    .join("");
}

// ---------------------------------------------------------------------------
// Song loading
// ---------------------------------------------------------------------------
async function loadSongs(expression) {
  const errEl = document.getElementById("filter-error");
  errEl.classList.add("hidden");
  errEl.textContent = "";

  const url = expression
    ? `/api/songs?q=${encodeURIComponent(expression)}`
    : "/api/songs";
  const data = await api("GET", url);

  if (!data.ok) {
    errEl.textContent = data.error || "SQL error";
    errEl.classList.remove("hidden");
    return;
  }

  songs = data.songs;
  selectedIds.clear();
  renderTable();
}

// ---------------------------------------------------------------------------
// Table rendering
// ---------------------------------------------------------------------------
function renderTable() {
  const tableWrap  = document.getElementById("table-wrap");
  const emptyMsg   = document.getElementById("empty-msg");
  const resultCount = document.getElementById("result-count");

  if (songs.length === 0) {
    tableWrap.classList.add("hidden");
    emptyMsg.classList.remove("hidden");
    emptyMsg.innerHTML = "No songs matched.";
    resultCount.classList.add("hidden");
    updateSelectedCount();
    return;
  }

  emptyMsg.classList.add("hidden");
  tableWrap.classList.remove("hidden");
  resultCount.classList.remove("hidden");
  resultCount.textContent = `${songs.length} song${songs.length !== 1 ? "s" : ""}`;

  renderHead();
  renderBody();
  updateSelectedCount();
}

function renderHead() {
  const thead = document.getElementById("table-head");
  const attrHeaders = attributes
    .map(a => `<th title="${esc(a.name)}">${esc(a.name)}</th>`)
    .join("");
  const coreHeaders = CORE_COLS
    .map(c => `<th>${esc(c.label)}</th>`)
    .join("");

  thead.innerHTML = `<tr>
    <th class="th-check"><input type="checkbox" id="select-all"></th>
    ${coreHeaders}
    ${attrHeaders}
  </tr>`;

  document.getElementById("select-all").addEventListener("change", e => {
    const checked = e.target.checked;
    songs.forEach(s => checked ? selectedIds.add(s.video_id) : selectedIds.delete(s.video_id));
    document.querySelectorAll(".row-check").forEach(cb => { cb.checked = checked; });
    document.querySelectorAll("#table-body tr").forEach(tr => {
      tr.classList.toggle("selected", checked);
    });
    updateSelectedCount();
  });
}

function renderBody() {
  const tbody = document.getElementById("table-body");
  tbody.innerHTML = songs.map(renderRow).join("");
  attachBodyListeners();
}

function renderRow(song) {
  const vid = song.video_id;
  const sel = selectedIds.has(vid);

  const coreCells = CORE_COLS.map(col => {
    const raw = song[col.key];
    const display = col.format ? col.format(raw) : esc(String(raw ?? ""));
    return `<td title="${esc(String(raw ?? ""))}">${esc(display)}</td>`;
  }).join("");

  const attrCells = attributes.map(a => {
    const val = song[a.name];
    if (a.value_type === "boolean") {
      return `<td class="bool-cell editable" data-vid="${esc(vid)}" data-attr="${esc(a.name)}">
        <input type="checkbox" class="bool-cell-check" data-vid="${esc(vid)}" data-attr="${esc(a.name)}" ${val ? "checked" : ""}>
      </td>`;
    }
    return `<td class="editable" data-vid="${esc(vid)}" data-attr="${esc(a.name)}" data-vtype="${esc(a.value_type)}">
      <span class="cell-display">${esc(String(val ?? ""))}</span>
    </td>`;
  }).join("");

  return `<tr data-vid="${esc(vid)}" class="${sel ? "selected" : ""}">
    <td class="td-check">
      <input type="checkbox" class="row-check" data-vid="${esc(vid)}" ${sel ? "checked" : ""}>
    </td>
    ${coreCells}
    ${attrCells}
  </tr>`;
}

// ---------------------------------------------------------------------------
// Event listeners on tbody
// ---------------------------------------------------------------------------
function attachBodyListeners() {
  // Row selection checkboxes
  document.querySelectorAll(".row-check").forEach(cb => {
    cb.addEventListener("change", e => {
      const vid = e.target.dataset.vid;
      const tr = e.target.closest("tr");
      if (e.target.checked) { selectedIds.add(vid); tr.classList.add("selected"); }
      else { selectedIds.delete(vid); tr.classList.remove("selected"); }
      updateSelectedCount();
      syncSelectAll();
    });
  });

  // Boolean attribute cells
  document.querySelectorAll(".bool-cell-check").forEach(cb => {
    cb.addEventListener("change", async e => {
      const { vid, attr } = e.target.dataset;
      const val = e.target.checked ? 1 : 0;
      await saveAttr(vid, attr, val);
      updateSongLocal(vid, attr, val);
    });
  });

  // Scalar / enum cells — click to open editor
  document.querySelectorAll("td.editable[data-vtype]").forEach(td => {
    td.addEventListener("click", () => {
      if (td.querySelector("input, select")) return;
      openEditor(td);
    });
  });
}

function syncSelectAll() {
  const allChecked = songs.length > 0 && songs.every(s => selectedIds.has(s.video_id));
  const sa = document.getElementById("select-all");
  if (sa) sa.checked = allChecked;
}

// ---------------------------------------------------------------------------
// Inline cell editor
// ---------------------------------------------------------------------------
function openEditor(td) {
  const vid   = td.dataset.vid;
  const attr  = td.dataset.attr;
  const vtype = td.dataset.vtype;
  const meta  = attrByName[attr];
  const song  = songs.find(s => s.video_id === vid);
  const current = song ? song[attr] : null;
  const span  = td.querySelector(".cell-display");

  let input;

  if (vtype === "enum") {
    let allowed = [];
    try { allowed = JSON.parse(meta.allowed_values || "[]"); } catch {}
    input = document.createElement("select");
    input.className = "cell-select";
    input.innerHTML =
      `<option value="">—</option>` +
      allowed.map(v => `<option value="${esc(v)}" ${v === current ? "selected" : ""}>${esc(v)}</option>`).join("");
  } else {
    input = document.createElement("input");
    input.type = "number";
    input.className = "cell-input";
    if (meta.min_value != null) input.min = meta.min_value;
    if (meta.max_value != null) input.max = meta.max_value;
    input.step = "0.5";
    input.value = current ?? "";
  }

  if (span) span.style.display = "none";
  td.appendChild(input);
  input.focus();
  if (input.select) input.select();

  async function commit() {
    let newVal;
    if (vtype === "enum") {
      newVal = input.value || null;
    } else {
      newVal = input.value === "" ? null : parseFloat(input.value);
    }
    input.remove();
    if (span) {
      span.textContent = newVal ?? "";
      span.style.display = "";
    }
    if (newVal !== current) {
      await saveAttr(vid, attr, newVal);
      updateSongLocal(vid, attr, newVal);
    }
  }

  input.addEventListener("blur", commit);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); input.blur(); }
    if (e.key === "Escape") {
      input.removeEventListener("blur", commit);
      input.remove();
      if (span) span.style.display = "";
    }
  });
}

// ---------------------------------------------------------------------------
// Save helpers
// ---------------------------------------------------------------------------
async function saveAttr(vid, attr, value) {
  await api("PATCH", `/api/songs/${encodeURIComponent(vid)}`, { attr, value });
}

function updateSongLocal(vid, attr, value) {
  const song = songs.find(s => s.video_id === vid);
  if (song) song[attr] = value;
}

function updateSelectedCount() {
  document.getElementById("selected-count").textContent =
    `${selectedIds.size} selected`;
}

// ---------------------------------------------------------------------------
// Sync button
// ---------------------------------------------------------------------------
document.getElementById("btn-sync").addEventListener("click", async () => {
  const status = document.getElementById("sync-status");
  status.textContent = "Syncing…";
  try {
    const data = await api("POST", "/api/sync");
    status.textContent = data.ok
      ? `Done — ${data.count} songs`
      : `Error: ${data.error}`;
  } catch (err) {
    status.textContent = `Error: ${err.message}`;
  }
});

// ---------------------------------------------------------------------------
// Filter / Go
// ---------------------------------------------------------------------------
document.getElementById("btn-go").addEventListener("click", () => {
  loadSongs(document.getElementById("filter-input").value.trim());
});

document.getElementById("filter-input").addEventListener("keydown", e => {
  if (e.key === "Enter") document.getElementById("btn-go").click();
});

// ---------------------------------------------------------------------------
// Enrichment
// ---------------------------------------------------------------------------
document.getElementById("btn-enrich").addEventListener("click", async () => {
  const data = await api("POST", "/api/enrich/start");
  if (!data.ok) {
    document.getElementById("enrich-status").textContent = `Error: ${data.error}`;
    return;
  }
  document.getElementById("btn-enrich-stop").classList.remove("hidden");
  startEnrichPoll();
});

document.getElementById("btn-enrich-stop").addEventListener("click", async () => {
  await api("POST", "/api/enrich/stop");
});

function startEnrichPoll() {
  if (enrichPollTimer) clearInterval(enrichPollTimer);
  enrichPollTimer = setInterval(async () => {
    const data = await api("GET", "/api/enrich/status");
    const statusEl = document.getElementById("enrich-status");
    const stopBtn  = document.getElementById("btn-enrich-stop");
    statusEl.textContent = `${data.done} of ${data.total} complete`;
    if (!data.running) {
      clearInterval(enrichPollTimer);
      enrichPollTimer = null;
      stopBtn.classList.add("hidden");
      statusEl.textContent += " — done";
    }
  }, 1000);
}

// ---------------------------------------------------------------------------
// Playlist create / refresh
// ---------------------------------------------------------------------------
document.getElementById("btn-create-playlist").addEventListener("click", async () => {
  const name       = document.getElementById("playlist-name").value.trim();
  const expression = document.getElementById("filter-input").value.trim();
  const statusEl   = document.getElementById("playlist-status");

  if (!name) { statusEl.textContent = "Enter a playlist name."; return; }
  statusEl.textContent = "Working…";

  const data = await api("POST", "/api/playlist", { name, expression });
  statusEl.textContent = data.ok
    ? `${data.action} — ${data.playlist_id}`
    : `Error: ${data.error}`;
});

// ---------------------------------------------------------------------------
// Bulk apply
// ---------------------------------------------------------------------------
document.getElementById("btn-bulk-apply").addEventListener("click", async () => {
  if (selectedIds.size === 0) {
    document.getElementById("bulk-status").textContent = "Nothing selected.";
    return;
  }
  const attr    = document.getElementById("bulk-attr").value;
  const rawVal  = document.getElementById("bulk-value").value.trim();
  const meta    = attrByName[attr];
  const statusEl = document.getElementById("bulk-status");

  let value;
  if (meta?.value_type === "boolean") {
    value = (rawVal === "1" || rawVal.toLowerCase() === "true") ? 1 : 0;
  } else if (meta?.value_type === "scalar") {
    value = rawVal === "" ? null : parseFloat(rawVal);
  } else {
    value = rawVal || null;
  }

  statusEl.textContent = "Applying…";
  const data = await api("POST", "/api/songs/bulk", {
    video_ids: [...selectedIds],
    attr,
    value,
  });

  if (data.ok) {
    selectedIds.forEach(vid => updateSongLocal(vid, attr, value));
    refreshAttrCells(attr, value, meta);
    statusEl.textContent = `Set ${attr} = ${value ?? "null"} on ${selectedIds.size} songs.`;
  } else {
    statusEl.textContent = `Error: ${data.error}`;
  }
});

function refreshAttrCells(attr, value, meta) {
  selectedIds.forEach(vid => {
    const td = document.querySelector(`td[data-vid="${CSS.escape(vid)}"][data-attr="${CSS.escape(attr)}"]`);
    if (!td) return;
    if (meta?.value_type === "boolean") {
      const cb = td.querySelector("input[type='checkbox']");
      if (cb) cb.checked = !!value;
    } else {
      const span = td.querySelector(".cell-display");
      if (span) span.textContent = value ?? "";
    }
  });
}

document.getElementById("btn-deselect-all").addEventListener("click", () => {
  selectedIds.clear();
  document.querySelectorAll(".row-check").forEach(cb => { cb.checked = false; });
  document.querySelectorAll("#table-body tr").forEach(tr => tr.classList.remove("selected"));
  const sa = document.getElementById("select-all");
  if (sa) sa.checked = false;
  updateSelectedCount();
  document.getElementById("bulk-status").textContent = "";
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
(async () => {
  await loadAttributes();

  // Resume progress display if enrichment was already running
  const status = await api("GET", "/api/enrich/status");
  if (status.running) {
    document.getElementById("btn-enrich-stop").classList.remove("hidden");
    document.getElementById("enrich-status").textContent =
      `${status.done} of ${status.total} complete`;
    startEnrichPoll();
  }
})();
