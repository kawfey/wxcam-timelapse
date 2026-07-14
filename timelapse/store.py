"""Path layout for stored stills/timelapses + retention pruning.

Layout (see docs/plan.md):
    data/stills/<cam>/<YYYY-MM-DD>/<HHMMSS>.jpg
    data/timelapses/<cam>/<YYYY-MM-DD>.mp4

Filenames encode local wall-clock time; the date dir is the local-day the frame
belongs to, so the daily rollup is just "glob one date dir".
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .config import Settings

DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H%M%S"


@dataclass(frozen=True)
class Frame:
    path: Path
    when: datetime  # tz-aware local time parsed from the path


def still_path(settings: Settings, cam_slug: str, when: datetime) -> Path:
    """Absolute path a still captured at local `when` should be written to."""
    day = when.strftime(DATE_FMT)
    return settings.stills_dir / cam_slug / day / f"{when.strftime(TIME_FMT)}.jpg"


def timelapse_path(settings: Settings, cam_slug: str, day: str) -> Path:
    """Absolute path for a day's rendered timelapse (`day` = 'YYYY-MM-DD')."""
    return settings.timelapses_dir / cam_slug / f"{day}.mp4"


def _parse_frame(path: Path, tz) -> Frame | None:
    """Reconstruct the local capture time from <date>/<HHMMSS>.jpg."""
    try:
        day = path.parent.name
        t = path.stem
        when = datetime.strptime(f"{day} {t}", f"{DATE_FMT} {TIME_FMT}")
        return Frame(path=path, when=when.replace(tzinfo=tz))
    except ValueError:
        return None


def list_frames(
    settings: Settings,
    cam_slug: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[Frame]:
    """All stored frames for a camera, ordered oldest→newest, optionally bounded
    to [since, until] (tz-aware, inclusive)."""
    tz = settings.tz
    cam_dir = settings.stills_dir / cam_slug
    if not cam_dir.is_dir():
        return []
    frames: list[Frame] = []
    for jpg in cam_dir.glob("*/*.jpg"):
        fr = _parse_frame(jpg, tz)
        if fr is None:
            continue
        if since is not None and fr.when < since:
            continue
        if until is not None and fr.when > until:
            continue
        frames.append(fr)
    frames.sort(key=lambda fr: fr.when)
    return frames


def latest_frame(settings: Settings, cam_slug: str) -> Frame | None:
    frames = list_frames(settings, cam_slug)
    return frames[-1] if frames else None


def prune(settings: Settings, cam_slug: str, now: datetime | None = None) -> dict[str, int]:
    """Delete stills older than retain_hours and timelapses older than
    retain_days. Returns counts of what was removed."""
    tz = settings.tz
    now = now or datetime.now(tz)

    stills_cutoff = now - timedelta(hours=settings.retain_hours)
    removed_stills = 0
    cam_stills = settings.stills_dir / cam_slug
    if cam_stills.is_dir():
        for jpg in list(cam_stills.glob("*/*.jpg")):
            fr = _parse_frame(jpg, tz)
            if fr is not None and fr.when < stills_cutoff:
                jpg.unlink(missing_ok=True)
                jpg.with_suffix(".sha256").unlink(missing_ok=True)  # dedup sidecar
                removed_stills += 1
        _remove_empty_dirs(cam_stills)

    tl_cutoff = (now - timedelta(days=settings.retain_days)).date()
    removed_tl = 0
    cam_tl = settings.timelapses_dir / cam_slug
    if cam_tl.is_dir():
        for mp4 in list(cam_tl.glob("*.mp4")):
            try:
                day = datetime.strptime(mp4.stem, DATE_FMT).date()
            except ValueError:
                continue
            if day < tl_cutoff:
                mp4.unlink(missing_ok=True)
                removed_tl += 1

    return {"stills": removed_stills, "timelapses": removed_tl}


def _remove_empty_dirs(root: Path) -> None:
    """Drop now-empty <date> dirs left behind after pruning stills."""
    for child in root.iterdir():
        if child.is_dir() and not any(child.iterdir()):
            shutil.rmtree(child, ignore_errors=True)
