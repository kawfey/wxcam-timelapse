"""Nightly rollup: assemble a local-day's stills into an MP4 via ffmpeg.

This is the one place the MVP shells out to ffmpeg. The live viewer never does —
it cycles the stored JPEGs client-side (see docs/plan.md).
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from . import store
from .config import Settings

log = logging.getLogger("wxcam.rollup")


class RollupError(RuntimeError):
    pass


def _ffmpeg_available() -> bool:
    from shutil import which

    return which("ffmpeg") is not None


def build_day(
    settings: Settings, cam_slug: str, day: str, force: bool = False
) -> Path | None:
    """Encode data/stills/<cam>/<day>/*.jpg -> data/timelapses/<cam>/<day>.mp4.

    `day` is 'YYYY-MM-DD' (local). Returns the output path, or None if there were
    no stills for that day. Raises RollupError on ffmpeg failure.
    """
    if not _ffmpeg_available():
        raise RollupError("ffmpeg not found on PATH")

    day_dir = settings.stills_dir / cam_slug / day
    stills = sorted(day_dir.glob("*.jpg")) if day_dir.is_dir() else []
    if not stills:
        log.info("rollup: no stills for %s/%s, skipping", cam_slug, day)
        return None

    out = store.timelapse_path(settings, cam_slug, day)
    if out.exists() and not force:
        log.info("rollup: %s already exists, skipping (use force=True)", out.name)
        return out
    out.parent.mkdir(parents=True, exist_ok=True)

    # Feed ffmpeg an explicit concat list so frames are ordered by capture time and
    # gaps (dedup-skipped or failed grabs) don't matter — glob patterns can't do
    # arbitrary ordering portably.
    listfile = out.with_suffix(".txt")
    listfile.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in stills), encoding="utf-8"
    )

    cmd = [
        "ffmpeg", "-y",
        "-r", str(settings.rollup_fps),      # input framerate: each still = 1 frame
        "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        # even dims required by yuv420p; pad if a source is odd-sized
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-r", str(settings.rollup_fps),      # output framerate
        str(out),
    ]
    log.info("rollup: encoding %d stills -> %s", len(stills), out.name)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    listfile.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RollupError(f"ffmpeg failed ({proc.returncode}):\n{proc.stderr[-2000:]}")
    log.info("rollup: wrote %s (%d frames)", out, len(stills))
    return out


def yesterday(settings: Settings, now: datetime | None = None) -> str:
    """Local-date string for 'yesterday' — the day the 00:05 rollup finalizes."""
    now = now or datetime.now(settings.tz)
    return (now - timedelta(days=1)).strftime("%Y-%m-%d")
