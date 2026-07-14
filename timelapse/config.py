"""Load runtime config: config/settings.toml + config/cameras.csv.

The camera schema is copied from the stl-webcam-dashboard (see CLAUDE.md).
Only a subset of columns matters here; we keep the rest around untouched so the
CSV stays a drop-in from the dashboard.
"""
from __future__ import annotations

import csv
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

# Repo root = parent of the `timelapse/` package dir.
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


@dataclass(frozen=True)
class Camera:
    """One row of config/cameras.csv."""

    name: str
    page_url: str
    stream_url: str
    type: str
    status: str
    notes: str = ""
    # keep any extra columns verbatim so the CSV stays a dashboard drop-in
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        """Filesystem-safe id used in data paths and API params (e.g. 'dnr')."""
        return _slugify(self.name)


@dataclass(frozen=True)
class Settings:
    # capture
    interval_s: int
    cache_bust: bool
    dedup_identical: bool
    # retention
    retain_hours: int
    retain_days: int
    # rollup
    rollup_fps: int
    rollup_time: str  # "HH:MM" local
    # general
    timezone: str
    data_dir: Path

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def stills_dir(self) -> Path:
        return self.data_dir / "stills"

    @property
    def timelapses_dir(self) -> Path:
        return self.data_dir / "timelapses"


# A few well-known cameras get short, stable slugs; everything else is derived.
_SLUG_OVERRIDES = {
    "MO DNR Pollution Cam (St. Marys)": "dnr",
}


def _slugify(name: str) -> str:
    if name in _SLUG_OVERRIDES:
        return _SLUG_OVERRIDES[name]
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "_":
            out.append("_")
    return "".join(out).strip("_")


def load_cameras(path: Path | None = None) -> list[Camera]:
    path = path or (CONFIG_DIR / "cameras.csv")
    known = {"name", "page_url", "stream_url", "type", "status", "notes"}
    cameras: list[Camera] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            extra = {k: v for k, v in row.items() if k not in known and k}
            cameras.append(
                Camera(
                    name=row["name"].strip(),
                    page_url=row.get("page_url", "").strip(),
                    stream_url=row.get("stream_url", "").strip(),
                    type=row.get("type", "").strip(),
                    status=row.get("status", "").strip(),
                    notes=row.get("notes", "").strip(),
                    extra=extra,
                )
            )
    return cameras


def get_camera(name: str, cameras: list[Camera] | None = None) -> Camera:
    cameras = cameras if cameras is not None else load_cameras()
    for cam in cameras:
        if cam.name == name or cam.slug == _slugify(name) or cam.slug == name:
            return cam
    raise KeyError(f"camera not found in cameras.csv: {name!r}")


def capturable_cameras(cameras: list[Camera] | None = None) -> list[Camera]:
    """Cameras this MVP can actually capture: direct-JPEG stills that are live.
    Everything else (hls_direct, wetmet_embed, dacast_embed, nest_embed, index
    pages, ...) is deferred — see CLAUDE.md."""
    cameras = cameras if cameras is not None else load_cameras()
    return [c for c in cameras if c.type == "still_image" and c.status == "live"]


def load_settings(path: Path | None = None) -> Settings:
    path = path or (CONFIG_DIR / "settings.toml")
    with path.open("rb") as f:
        raw = tomllib.load(f)

    cap = raw.get("capture", {})
    ret = raw.get("retention", {})
    roll = raw.get("rollup", {})
    gen = raw.get("general", {})

    data_dir = Path(gen.get("data_dir", "data"))
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir

    return Settings(
        interval_s=int(cap.get("interval_s", 60)),
        cache_bust=bool(cap.get("cache_bust", True)),
        dedup_identical=bool(cap.get("dedup_identical", True)),
        retain_hours=int(ret.get("retain_hours", 48)),
        retain_days=int(ret.get("retain_days", 30)),
        rollup_fps=int(roll.get("fps", 60)),
        rollup_time=str(roll.get("rollup_time", "00:05")),
        timezone=str(gen.get("timezone", "America/Chicago")),
        data_dir=data_dir,
    )
