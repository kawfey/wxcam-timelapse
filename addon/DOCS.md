# wxcam Timelapse

Captures webcam stills on a schedule, burns a datetime + title overlay, keeps a
rolling window, auto-assembles a daily timelapse, and serves a browser viewer that
plays recent stills back at an adjustable speed. Seeded with the St. Louis camera
set (MO DNR + 18 KMOV Ford Skycam feeds); any `still_image` camera works.

## Install

1. In Home Assistant: **Settings → Add-ons → Add-on Store**.
2. Top-right menu (⋮) → **Repositories** → add
   `https://github.com/kawfey/wxcam-timelapse` → **Add**.
3. Find **wxcam Timelapse** in the store, open it, and click **Install**
   (the first build fetches the app + ffmpeg, so give it a few minutes).
4. Click **Start**. The viewer is at `http://<your-ha-host>:8848`.

## Configuration

| Option         | Default                  | Meaning                                                        |
| -------------- | ------------------------ | -------------------------------------------------------------- |
| `interval_s`   | `60`                     | Seconds between capture rounds (all cameras share one loop).   |
| `retain_hours` | `48`                     | How long stills are kept before pruning (the rolling window).  |
| `retain_days`  | `30`                     | How long rendered daily timelapses are kept.                   |
| `timezone`     | `America/Chicago`        | Overlay clock + daily-rollup boundary (local midnight).        |
| `data_dir`     | `/media/wxcam-timelapse` | Where stills + timelapses are written (under HA's shared media). |

Because `data_dir` lives under `/media`, the captured stills and rendered
timelapses show up in Home Assistant's **Media** panel and can be reused by your
webcam dashboard — no copying between containers.

### Storage note

Each still is ~150 KB. With 19 cameras at a 60 s interval and a 48 h window, plan
for a few GB of rolling stills plus the daily timelapse archive. Put `/media` on an
SSD, not the SD card, for anything long-running.

## What runs inside

A single `uvicorn` process serves the viewer/API **and** runs the capture +
nightly-rollup scheduler in-process (`WXCAM_RUN_SCHEDULER=1`). ffmpeg is used only
for the nightly daily-timelapse encode; the live viewer plays stored JPEGs
client-side, so changing window/speed is instant.

## Adding or removing cameras

Cameras are auto-discovered from `config/cameras.csv` in the app (any row with
`type=still_image` and `status=live`). To change the set today, edit that file in
the repo and rebuild the add-on. A future version will expose the camera list in
the add-on's own config directory for editing without a rebuild.

## Not yet included

Stream (HLS) cameras, the range exporter, and YouTube archiving are on the
roadmap — see `docs/plan.md` in the repo. This add-on covers the direct-JPEG
still cameras end-to-end.
