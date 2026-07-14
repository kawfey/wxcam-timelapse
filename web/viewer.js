// Client-side timelapse viewer: fetch a subsampled window of stored JPEG URLs
// from /api/frames and cycle an <img> over them at a chosen fps. No re-encode —
// changing window/speed/start is instant (see docs/plan.md).

const $ = (id) => document.getElementById(id);

const els = {
  cam: $("cam"),
  frame: $("frame"),
  stageMsg: $("stage-msg"),
  ts: $("ts"),
  seek: $("seek"),
  pos: $("pos"),
  count: $("count"),
  play: $("play"),
  window: $("window"),
  speed: $("speed"),
  loop: $("loop"),
  reload: $("reload"),
  meta: $("meta"),
};

const HOLD_MS = 3000;  // pause this long on the final frame before looping

const state = {
  frames: [],      // { url, ts }
  images: [],      // preloaded Image objects (same index as frames)
  idx: 0,
  playing: false,
  timer: null,     // per-frame interval
  holdTimer: null, // 3s hold at end of a loop
  loop: true,
  tz: "local",
};

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

async function loadCameras() {
  const data = await fetchJSON("/api/cameras");
  state.tz = data.timezone || "local";
  els.cam.innerHTML = "";
  for (const c of data.cameras) {
    const opt = document.createElement("option");
    opt.value = c.slug;
    opt.textContent = c.name;
    els.cam.appendChild(opt);
  }
  if (!data.cameras.length) {
    setMessage("No cameras configured.");
  }
}

function setMessage(msg) {
  els.stageMsg.textContent = msg || "";
  els.stageMsg.style.display = msg ? "flex" : "none";
}

function fmtTs(iso) {
  // Render in the CAMERA's timezone, not the viewer's browser zone — otherwise
  // a viewer in another tz sees the wrong wall-clock time.
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: state.tz,
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    }).format(d);
    return parts.replace(", ", " ");  // "2026-07-13, 10:35:37" -> "2026-07-13 10:35:37"
  } catch {
    return iso;
  }
}

async function loadWindow() {
  stop();
  const cam = els.cam.value;
  if (!cam) return;
  const hours = els.window.value;
  setMessage("Loading frames…");
  let data;
  try {
    data = await fetchJSON(`/api/frames?cam=${encodeURIComponent(cam)}&hours=${hours}&max=900`);
  } catch (e) {
    setMessage(`Failed to load frames: ${e.message}`);
    return;
  }
  state.frames = data.frames || [];
  state.idx = 0;

  els.seek.max = Math.max(0, state.frames.length - 1);
  els.seek.value = 0;
  els.count.textContent = `/ ${state.frames.length} frames`;

  if (!state.frames.length) {
    state.images = [];
    els.frame.removeAttribute("src");
    setMessage(`No stills captured in the last ${hours} h yet.`);
    updateMeta(data);
    return;
  }

  // Preload images so playback doesn't stutter on first pass.
  setMessage(`Preloading ${state.frames.length} frames…`);
  state.images = state.frames.map((f) => {
    const img = new Image();
    img.src = f.url;
    return img;
  });
  await Promise.race([
    Promise.allSettled(state.images.slice(0, 12).map(imgReady)),
    delay(2500),
  ]);

  setMessage("");
  showFrame(0);
  updateMeta(data);
  play();
}

function imgReady(img) {
  return new Promise((res) => {
    if (img.complete) return res();
    img.onload = img.onerror = () => res();
  });
}

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

function showFrame(i) {
  if (!state.frames.length) return;
  state.idx = ((i % state.frames.length) + state.frames.length) % state.frames.length;
  const f = state.frames[state.idx];
  els.frame.src = f.url;
  els.ts.textContent = fmtTs(f.ts);
  els.seek.value = state.idx;
  els.pos.textContent = state.idx + 1;
}

function _clearTimers() {
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  if (state.holdTimer) { clearTimeout(state.holdTimer); state.holdTimer = null; }
}

function _startInterval() {
  const fps = Number(els.speed.value) || 24;
  state.timer = setInterval(advance, 1000 / fps);
}

function advance() {
  if (state.idx >= state.frames.length - 1) {
    // On the final frame.
    if (!state.loop) { stop(); return; }        // play once: stop at the end
    // Loop: hold on the final frame for HOLD_MS, then restart from the top.
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    state.holdTimer = setTimeout(() => {
      state.holdTimer = null;
      if (!state.playing) return;
      showFrame(0);
      _startInterval();
    }, HOLD_MS);
    return;
  }
  showFrame(state.idx + 1);
}

function play() {
  if (!state.frames.length) return;
  _clearTimers();
  state.playing = true;
  els.play.textContent = "⏸";
  // If parked on the last frame (e.g. after a play-once), restart from the top.
  if (state.idx >= state.frames.length - 1) showFrame(0);
  _startInterval();
}

function stop() {
  _clearTimers();
  state.playing = false;
  els.play.textContent = "▶︎";
}

function togglePlay() {
  state.playing ? stop() : play();
}

function updateMeta(data) {
  const parts = [];
  if (data) {
    parts.push(`${data.returned}/${data.total_in_window} frames (subsampled)`);
    parts.push(`tz ${data.timezone}`);
  }
  els.meta.textContent = parts.join(" · ") || "—";
}

// --- events ---
els.play.addEventListener("click", togglePlay);
els.reload.addEventListener("click", loadWindow);
els.window.addEventListener("change", loadWindow);
els.cam.addEventListener("change", loadWindow);
els.speed.addEventListener("change", () => {
  if (state.playing) { stop(); play(); }  // re-arm timer at new fps
});
els.loop.addEventListener("change", () => {
  state.loop = els.loop.value === "loop";
});
els.seek.addEventListener("input", () => {
  stop();
  showFrame(Number(els.seek.value));
});

document.addEventListener("keydown", (e) => {
  if (e.code === "Space") { e.preventDefault(); togglePlay(); }
  else if (e.code === "ArrowRight") { stop(); showFrame(state.idx + 1); }
  else if (e.code === "ArrowLeft") { stop(); showFrame(state.idx - 1); }
});

(async function init() {
  try {
    state.loop = els.loop.value === "loop";
    await loadCameras();
    await loadWindow();
  } catch (e) {
    setMessage(`Init failed: ${e.message}`);
  }
})();
