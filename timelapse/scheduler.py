"""APScheduler entry point + a CLI for running pieces by hand.

    python -m timelapse.scheduler run              # start capture loop + nightly rollup
    python -m timelapse.scheduler capture           # one capture round, all cameras, then exit
    python -m timelapse.scheduler capture <cam>     # one capture, single camera (name or slug)
    python -m timelapse.scheduler rollup [YYYY-MM-DD]      # build a day, all cameras
    python -m timelapse.scheduler rollup [YYYY-MM-DD] <cam>  # build a day, single camera
    python -m timelapse.scheduler prune             # run retention once, all cameras
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

import httpx

from . import capture, rollup, store
from .config import Camera, capturable_cameras, get_camera, load_settings

log = logging.getLogger("wxcam")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _capture_one(cam: Camera, settings, client: httpx.Client) -> None:
    try:
        frame = capture.capture_once(cam, settings, client=client)
    except (capture.CaptureError, httpx.HTTPError) as e:
        log.error("capture failed for %s: %s", cam.slug, e)
        return
    if frame is None:
        log.info("capture: %s frame skipped (dedup)", cam.slug)
    removed = store.prune(settings, cam.slug)
    if removed["stills"] or removed["timelapses"]:
        log.info("prune: %s removed %s", cam.slug, removed)


def do_capture(cam_name: str | None = None) -> None:
    settings = load_settings()
    cams = [get_camera(cam_name)] if cam_name else capturable_cameras()
    if not cams:
        log.warning("capture: no capturable cameras configured")
        return
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        for cam in cams:
            _capture_one(cam, settings, client)


def do_rollup(day: str | None = None, cam_name: str | None = None) -> None:
    settings = load_settings()
    cams = [get_camera(cam_name)] if cam_name else capturable_cameras()
    day = day or rollup.yesterday(settings)
    for cam in cams:
        try:
            out = rollup.build_day(settings, cam.slug, day)
        except rollup.RollupError as e:
            log.error("rollup failed for %s: %s", cam.slug, e)
            continue
        if out is None:
            log.info("rollup: nothing to build for %s/%s", cam.slug, day)
        else:
            log.info("rollup: %s", out)


def do_prune() -> None:
    settings = load_settings()
    for cam in capturable_cameras():
        log.info("prune: %s removed %s", cam.slug, store.prune(settings, cam.slug))


def do_run() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    settings = load_settings()
    cams = capturable_cameras()
    hh, mm = (int(x) for x in settings.rollup_time.split(":"))

    sched = BlockingScheduler(timezone=settings.timezone)
    sched.add_job(
        do_capture,
        IntervalTrigger(seconds=settings.interval_s),
        id="capture",
        next_run_time=datetime.now(settings.tz),  # fire immediately
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        do_rollup,
        CronTrigger(hour=hh, minute=mm, timezone=settings.timezone),
        id="rollup",
    )
    log.info(
        "scheduler: capturing %d camera(s) [%s] every %ss; nightly rollup at %s %s",
        len(cams), ", ".join(c.slug for c in cams),
        settings.interval_s, settings.rollup_time, settings.timezone,
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopped")


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="timelapse.scheduler")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="start capture loop + nightly rollup")
    p_cap = sub.add_parser("capture", help="capture one round, then exit")
    p_cap.add_argument("cam", nargs="?", default=None, help="camera name/slug (default: all)")
    p_roll = sub.add_parser("rollup", help="build a day's timelapse(s)")
    p_roll.add_argument("day", nargs="?", default=None, help="YYYY-MM-DD (default: yesterday)")
    p_roll.add_argument("cam", nargs="?", default=None, help="camera name/slug (default: all)")
    sub.add_parser("prune", help="run retention once, all cameras")

    args = parser.parse_args(argv)
    if args.cmd == "run":
        do_run()
    elif args.cmd == "capture":
        do_capture(args.cam)
    elif args.cmd == "rollup":
        do_rollup(args.day, args.cam)
    elif args.cmd == "prune":
        do_prune()
    return 0


if __name__ == "__main__":
    sys.exit(main())
