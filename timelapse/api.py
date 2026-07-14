"""FastAPI: serve stored stills + a subsampled /frames window for the viewer.

The viewer is pure client-side JPEG cycling, so the server's only jobs are:
  * GET /api/frames  -> ordered, evenly-subsampled list of {url, ts} for a window
  * GET /api/cameras -> the still cameras available
  * static /stills/... (the JPEGs) and the web/ viewer at /
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import store
from .config import REPO_ROOT, Camera, load_cameras, load_settings

settings = load_settings()
_all_cameras = load_cameras()

app = FastAPI(title="wxcam-timelapse", version="0.1")


def _still_cameras() -> list[Camera]:
    return [c for c in _all_cameras if c.type == "still_image" and c.status == "live"]


def _camera_or_404(slug: str) -> Camera:
    for c in _all_cameras:
        if c.slug == slug:
            return c
    raise HTTPException(status_code=404, detail=f"unknown camera: {slug}")


def _subsample(frames: list[store.Frame], max_frames: int) -> list[store.Frame]:
    """Evenly pick at most `max_frames` from `frames` (Windy-style), always
    keeping the first and last."""
    n = len(frames)
    if max_frames <= 0 or n <= max_frames:
        return frames
    if max_frames == 1:
        return [frames[-1]]  # single frame -> most recent
    # even indices across [0, n-1]
    idx = [round(i * (n - 1) / (max_frames - 1)) for i in range(max_frames)]
    seen: set[int] = set()
    out = []
    for i in idx:
        if i not in seen:
            seen.add(i)
            out.append(frames[i])
    return out


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "cameras": [c.slug for c in _still_cameras()]}


@app.get("/api/cameras")
def cameras() -> dict:
    return {
        "cameras": [
            {"slug": c.slug, "name": c.name, "type": c.type} for c in _still_cameras()
        ],
        "timezone": settings.timezone,
    }


@app.get("/api/frames")
def frames(
    cam: str = Query(..., description="camera slug, e.g. 'dnr'"),
    hours: float = Query(12.0, gt=0, le=24 * 30, description="window size (hours back)"),
    max: int = Query(900, gt=0, le=5000, description="max frames after subsampling"),
) -> dict:
    """Ordered JPEG URLs + timestamps for the last `hours`, subsampled to `max`."""
    camera = _camera_or_404(cam)
    now = datetime.now(settings.tz)
    since = now - timedelta(hours=hours)
    window = store.list_frames(settings, camera.slug, since=since)
    picked = _subsample(window, max)

    def url_for(fr: store.Frame) -> str:
        rel = fr.path.relative_to(settings.stills_dir).as_posix()
        return f"/stills/{rel}"

    return {
        "cam": camera.slug,
        "name": camera.name,
        "timezone": settings.timezone,
        "total_in_window": len(window),
        "returned": len(picked),
        "frames": [
            {"url": url_for(fr), "ts": fr.when.isoformat()} for fr in picked
        ],
    }


@app.get("/api/timelapses")
def timelapses(cam: str = Query(...)) -> dict:
    """List rendered daily timelapses for a camera (newest first)."""
    camera = _camera_or_404(cam)
    cam_dir = settings.timelapses_dir / camera.slug
    days = []
    if cam_dir.is_dir():
        for mp4 in sorted(cam_dir.glob("*.mp4"), reverse=True):
            days.append({"day": mp4.stem, "url": f"/timelapses/{camera.slug}/{mp4.name}"})
    return {"cam": camera.slug, "timelapses": days}


def _mount_static() -> None:
    settings.stills_dir.mkdir(parents=True, exist_ok=True)
    settings.timelapses_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/stills", StaticFiles(directory=settings.stills_dir), name="stills")
    app.mount(
        "/timelapses", StaticFiles(directory=settings.timelapses_dir), name="timelapses"
    )
    web_dir = REPO_ROOT / "web"
    if web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")


_mount_static()
