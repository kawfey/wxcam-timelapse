"""wxcam-timelapse — capture, overlay, store, rollup, schedule, serve.

Scaffold only. Planned modules (see docs/plan.md):
    config.py     load cameras.csv + settings.toml
    capture.py    fetch a still (direct JPEG for MVP) -> overlay -> save
    overlay.py    Pillow: burn local-time datetime + camera title
    store.py      path layout + retention prune (+ optional SQLite index)
    rollup.py     nightly: assemble a day's stills -> mp4 via ffmpeg
    scheduler.py  APScheduler: capture job + nightly rollup
    api.py        FastAPI: serve stills, /frames window list, /health
"""
