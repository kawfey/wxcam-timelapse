# wxcam-timelapse — context for Claude

Timelapse system for weather/webcam feeds: capture stills on a schedule, burn a
datetime + title overlay, keep a rolling window, auto-assemble a daily timelapse,
and play recent stills back in the browser at an adjustable speed (plus a future
exporter). Any camera can be used; **the STL set is just what we start with.**

**Status: MVP implemented** (single still camera, end-to-end). The approved plan
is in [`docs/plan.md`](docs/plan.md); the deferred/post-MVP items there are the
remaining roadmap. Run it with the venv: `.venv/bin/python -m timelapse.scheduler
run` (capture loop + nightly rollup) and `.venv/bin/uvicorn timelapse.api:app
--port 8848` (viewer + API). Requires Python 3.11+ (repo venv is 3.13) and ffmpeg.

## Provenance
Spun off from the **stl-webcams dashboard** (github.com/kawfey/stl-webcam-dashboard,
local `~/claude-dev/stl-webcams`). The camera list in `config/cameras.csv` is copied
from that dashboard's `data/cameras.csv` — same schema. Columns that matter here:
`name`, `page_url`, `stream_url`, `type`, `render`, `status`, `notes`.

## MVP
One camera, stills-only, local, Python + ffmpeg. MVP camera = **MO DNR Pollution
Cam (St. Marys)** — a `still_image` (direct JPEG), updates ~60 s.

## Key architecture (don't lose this)
The **rolling viewer plays stored JPEGs client-side** (cycle `<img>` over a window at
a chosen fps, subsampled to a target frame count Windy-style) — so changing window/
speed/start is instant and free. **ffmpeg is only for the daily rollup + the future
exporter.** Split "viewing" (cheap, client) from "produce a file" (ffmpeg).

## Camera capture idiosyncrasies (the stuff that bites)
Capture method is chosen by the cameras.csv `type` column:

- **`still_image` (direct JPEG — MVP path):** HTTP GET the `stream_url`.
  - These sources update the image **in place at the same URL**, so you MUST
    **cache-bust** (append `?_t=<ms>` / `&_t=`) or you may refetch an identical
    cached frame.
  - **MO DNR** carries a Drupal **`?itok=` token**. The *bare* URL 404s whenever the
    image-style derivative cache is flushed; the token URL is path-stable but the
    token *can* rotate. On a 404, re-scrape the page (`page_url`,
    dnr.mo.gov/.../st-louis-camera) for the current `framegrab.jpg?itok=` URL.
  - **KMOV Ford Skycam** stills live on `webpubcontent.gray.tv`, stable URLs updated
    in place, ~minutes cadence.
- **`hls_direct` (SLU):** unauthenticated Pixelcaster `.m3u8` → `ffmpeg -i <m3u8>
  -frames:v 1 out.jpg`. Note SLU is a **PTZ on a 4-position schedule**, so its
  timelapse will jump between views — expected, not a bug.
- **`wetmet_embed` (12 cams):** HLS is **signed per request** (`wmsAuthSign`, ~30-min
  validity) — there is no stable m3u8. To grab a frame: fetch the `page_url`
  (`api.wetmet.net/widgets/stream/frame.php?uid=...`) HTML, **regex the signed m3u8
  URL out of it**, then ffmpeg one frame. (Aside: the embedded *player* goes black at
  ~300 s and renders 640×360 — irrelevant if you re-scrape per grab.)
- **`dacast_embed` (Arch E/W):** signed HLS behind a player; harder to extract. Defer.
- **`nest_embed` (3):** `status: offline`/dead → skip.
- **`embed_page` / `index_page` / `render: link` / `skip`** (EarthCam, KMOV live,
  SkyFOX, index pages): not directly capturable → skip.

## Cadence & storage notes
- **Match capture interval to the source's real update rate** per camera (stills
  ~1–5 min; oversampling just writes duplicate frames). Consider **dedup-by-hash**
  (skip saving if identical to the previous frame) to save storage.
- Timezone is **America/Chicago (Central)** for overlays and the daily-rollup
  boundary (local midnight). Keep it configurable (any camera, any tz later).
- For the stream phase, **go2rtc** normalizes HLS/RTSP → instant snapshot endpoints
  and erases most of the per-grab ffmpeg cost.

## Estimates (grounded)
Full STL set (~34 live cams) ≈ 29 GB rolling stills (48 h) + ~34 GB timelapse archive
(30 d) → a Pi 5 + 256 GB–1 TB SSD handles it. The 1-cam MVP is a few MB/day.
