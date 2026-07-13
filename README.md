# wxcam-timelapse

Capture stills from webcams on a schedule, overlay a timestamp + title, keep a
rolling window, and auto-build a daily timelapse — with a browser viewer that
plays recent stills back at an adjustable speed, plus a future exporter for
arbitrary date ranges.

Any camera works; it's seeded with the St. Louis set from the
[stl-webcams dashboard](https://github.com/kawfey/stl-webcam-dashboard).

> **Status: scaffold.** Nothing is implemented yet — see [`docs/plan.md`](docs/plan.md)
> for the approved MVP plan and [`CLAUDE.md`](CLAUDE.md) for camera capture quirks.

## MVP (planned)
One camera (MO DNR still cam), stills-only, running locally:
capture → overlay → store → nightly timelapse → rolling browser viewer → prune.
Python + ffmpeg. Runs on a Mac first; containerize for a Pi / cheap cloud later.

## Layout
```
config/       cameras.csv (camera list) + settings.toml
timelapse/    capture, overlay, store, rollup, scheduler, api (Python)
web/          rolling viewer (client-side JPEG cycling)
docs/plan.md  the approved plan
data/         stills/ + timelapses/ (gitignored, created at runtime)
```

## Why not just use Windy?
Windy's webcam playback is the UX reference, but it captures coarsely (~10 min)
and can't export. We capture finely and own the stills, so we can export.
