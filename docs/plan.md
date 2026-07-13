# Webcam Timelapse System — MVP Plan

## Context
Spun off from the STL webcam **dashboard** (which shows live feeds + a map). This is a
separate, backend-heavy project: continuously capture stills from webcams, burn a
datetime + title overlay, retain a rolling window, and auto-assemble a daily timelapse —
with a browser viewer that plays the recent stills back at an adjustable speed, plus a
future exporter for arbitrary ranges. Windy.com's webcam playback is the UX north star
(scrubber + play + speed), but with export.

**Decisions (from user):** new standalone repo · MVP = one camera, stills-only, local ·
Python + ffmpeg · runs on the local Mac first, containerized for Pi/cloud later.

**Key architectural insight:** the rolling viewer plays the stored **JPEGs directly in
the browser** (cycle an `<img>` over a chosen window at a chosen frame rate). So changing
window `n` / speed `s` / start time is instant and free — no re-encode. Server-side ffmpeg
is only needed for the **daily rollup** and the (later) **exporter**. This cleanly splits
"live viewing" (cheap, client-side) from "produce a file" (ffmpeg).

**Windy.com findings (what we borrow / how we differ):** Windy captures every ~10 min and
caps its "last 24 h" playback at ~25 images, played as a **client-side slideshow, not a
video** — which validates our JPEG-cycling viewer. Its image URLs are token-expiring
(10 min free / 24 h pro), which is exactly *why Windy can't export and we can* — we own our
stills. Two things to steal: (1) **capture much finer** (30–60 s vs 10 min) — that's our
differentiator (smooth timelapses) and the main storage/CPU driver; (2) the **viewer
subsamples** to a target frame count for fast load + smooth playback, while the full-res
stills stay reserved for the exporter. Windy also tiers timelapses day/month/lifetime — a
roadmap cue (below).

## MVP scope (build this first)
One direct-JPEG still camera — **MO DNR Pollution Cam** (`still_image`, updates ~60 s,
known-good URL incl. the `?itok=` token). Prove the whole loop locally:
capture → overlay → store → nightly timelapse → rolling browser viewer → retention prune.
No HLS/stream extraction, no exporter, no YouTube, no multi-cam yet (all deferred below).

## Repo scaffold (`wxcam-timelapse`, new repo)
```
wxcam-timelapse/
  README.md
  pyproject.toml           # pillow, httpx, apscheduler, fastapi, uvicorn
  config/
    cameras.csv            # reuse the dashboard's schema (name,url,type,...); MVP: DNR row
    settings.toml          # capture_interval_s, retain_hours (y), retain_days (z), tz, paths
  timelapse/
    config.py              # load cameras.csv + settings.toml
    capture.py             # fetch still (direct JPEG for MVP) -> overlay -> save
    overlay.py             # Pillow: burn local-time datetime + camera title/details
    store.py               # path layout + retention prune (+ optional SQLite index)
    rollup.py              # nightly: assemble a day's stills -> mp4 via ffmpeg
    scheduler.py           # APScheduler: capture job (every X s) + nightly rollup
    api.py                 # FastAPI: static stills, /frames window list, /health
  web/
    index.html  viewer.js  styles.css   # rolling viewer (client-side <img> cycling)
  data/                    # gitignored
    stills/<cam>/<YYYY-MM-DD>/<HHMMSS>.jpg
    timelapses/<cam>/<YYYY-MM-DD>.mp4
  .gitignore               # data/, __pycache__/
  docker-compose.yml       # (later) capture + web (+ go2rtc later)
```

## How the MVP works
1. **Capture** (`scheduler.py` → `capture.py`, every `capture_interval_s`, default 60 s for DNR):
   `httpx` GET the JPEG → `overlay.py` (Pillow) burns bottom-strip `YYYY-MM-DD HH:MM:SS CT` +
   camera title → save to `data/stills/dnr/<date>/<HHMMSS>.jpg`. Overlay-at-capture so every
   still is self-documenting.
2. **Retention** (`store.py`, runs each capture or hourly): delete stills older than
   `retain_hours` (y); delete timelapses older than `retain_days` (z).
3. **Nightly rollup** (`rollup.py`, APScheduler at 00:05 local): for the finished day,
   `ffmpeg -framerate 60 -pattern_type glob -i 'data/stills/dnr/<date>/*.jpg'
   -c:v libx264 -pix_fmt yuv420p data/timelapses/dnr/<date>.mp4`. 24 h of 60 s stills →
   1440 frames → ~24 s clip. (Later: burn a date via `drawtext`, upload.)
4. **Viewer** (`web/` + `api.py`): `/frames?cam=dnr&hours=n&max=<target>` returns the ordered
   JPEG URLs (+ timestamps) for the last `n` hours, **evenly subsampled to `max` frames**
   (Windy-style — e.g. ~600–1200) so a 12 h window loads fast and plays smoothly instead of
   pulling every still; full-res stills stay for the exporter. `viewer.js` preloads and cycles
   an `<img>` at a playback fps derived from speed `s` (loop length = frames / fps), shows the
   current frame's timestamp, and has play/pause + speed + window controls. Stills served via
   FastAPI `StaticFiles` from `data/stills/`.

## Config reuse
Read the dashboard's `cameras.csv` (its `name`/`url`/`type`/`render` columns already
distinguish `still_image` vs `hls`/`iframe`). MVP uses only the DNR row; the stream rows
are what the go2rtc phase (below) will consume — no schema changes needed.

## Deferred (post-MVP, in rough order)
- **Stream capture:** add `go2rtc` (Docker) to normalize HLS/RTSP → instant `/api/frame.jpeg`
  snapshots; fall back to `ffmpeg -i <m3u8> -frames:v 1`. **wetmet** needs re-scraping the
  signed `wmsAuthSign` URL out of `frame.php` per grab (30-min validity).
- **Exporter page:** inputs = start, end, speed×, fps (or start/end/duration → solve speed);
  show computed duration + **estimated filesize** with warnings for absurd size/duration;
  server-side ffmpeg renders the range to a downloadable MP4.
- **YouTube archive:** Data API resumable upload of each daily timelapse.
- **Timelapse tiers (Windy parity+):** beyond the daily rollup, add month/lifetime rollups
  (assembled from daily clips or subsampled stills).
- **Scale:** all ~34 live cams; SQLite capture index for fast range queries; parallel encodes.
- **Deploy:** Docker Compose → Pi 5 + SSD; cheap-cloud path = ~$5/mo VPS + Cloudflare R2 /
  Backblaze for archives + YouTube as free CDN.
- **Formats/dims:** keep source resolution; add output-format options later.

## Estimates (why the Pi is enough)
Full set ~34 live cams (~19 direct-JPEG stills @60 s + ~15 streams @30 s, ~150 KB/still, 720p):
- Stills churn ≈ **15 GB/day** (written + pruned); 48 h rolling buffer ≈ **29 GB** resident.
- Daily timelapse files ≈ 20–40 MB each → **~1 GB/day**; 30-day archive ≈ **34 GB**
  (before offloading to YouTube/object storage).
- Download ≈ 15 GB/day ≈ **1.4 Mbps** avg. CPU: direct-JPEG ≈ free; HLS extraction is the
  cost (go2rtc snapshots erase most of it); daily encode ≈ 30–60 min off-peak, parallel.
- → **Pi 5 + 256 GB–1 TB SSD** handles the full set; the 1-cam MVP is a few MB/day, runs anywhere.

## Verification (MVP, end-to-end)
1. Run `scheduler.py` locally; after a few minutes confirm timestamped JPEGs accumulate under
   `data/stills/dnr/<date>/`.
2. Trigger `rollup.py` for a day with N stills; confirm the MP4 plays and duration ≈ N/60 s.
3. Serve via FastAPI, open the viewer; confirm it cycles the last-`n`-hours stills at speed `s`,
   shows timestamps, and play/pause/speed/window controls work.
4. Set `retain_hours` low (e.g. 1) and confirm old stills get pruned.
