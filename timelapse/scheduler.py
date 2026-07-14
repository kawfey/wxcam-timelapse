"""APScheduler entry point + a CLI for running pieces by hand.

    python -m timelapse.scheduler run        # start capture loop + nightly rollup
    python -m timelapse.scheduler capture    # one capture, then exit
    python -m timelapse.scheduler rollup [YYYY-MM-DD]  # build a day (default: yesterday)
    python -m timelapse.scheduler prune      # run retention once
"""
from __future__ import annotations

import argparse
import logging
import sys

import httpx

from . import capture, rollup, store
from .config import get_camera, load_settings

log = logging.getLogger("wxcam")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def do_capture() -> None:
    settings = load_settings()
    cam = get_camera(settings.mvp_camera)
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        try:
            frame = capture.capture_once(cam, settings, client=client)
        except (capture.CaptureError, httpx.HTTPError) as e:
            log.error("capture failed for %s: %s", cam.slug, e)
            return
    if frame is None:
        log.info("capture: frame skipped (dedup)")
    # prune opportunistically so a long-running loop stays within the window
    removed = store.prune(settings, cam.slug)
    if removed["stills"] or removed["timelapses"]:
        log.info("prune removed %s", removed)


def do_rollup(day: str | None = None) -> None:
    settings = load_settings()
    cam = get_camera(settings.mvp_camera)
    day = day or rollup.yesterday(settings)
    try:
        out = rollup.build_day(settings, cam.slug, day)
    except rollup.RollupError as e:
        log.error("rollup failed: %s", e)
        return
    if out is None:
        log.info("rollup: nothing to build for %s", day)
    else:
        log.info("rollup: %s", out)


def do_prune() -> None:
    settings = load_settings()
    cam = get_camera(settings.mvp_camera)
    log.info("prune removed %s", store.prune(settings, cam.slug))


def do_run() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    settings = load_settings()
    cam = get_camera(settings.mvp_camera)
    hh, mm = (int(x) for x in settings.rollup_time.split(":"))

    sched = BlockingScheduler(timezone=settings.timezone)
    sched.add_job(
        do_capture,
        IntervalTrigger(seconds=settings.interval_s),
        id="capture",
        next_run_time=__import__("datetime").datetime.now(settings.tz),  # fire immediately
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        do_rollup,
        CronTrigger(hour=hh, minute=mm, timezone=settings.timezone),
        id="rollup",
    )
    log.info(
        "scheduler: capturing %s every %ss; nightly rollup at %s %s",
        cam.slug, settings.interval_s, settings.rollup_time, settings.timezone,
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
    sub.add_parser("capture", help="capture one still, then exit")
    p_roll = sub.add_parser("rollup", help="build a day's timelapse")
    p_roll.add_argument("day", nargs="?", default=None, help="YYYY-MM-DD (default: yesterday)")
    sub.add_parser("prune", help="run retention once")

    args = parser.parse_args(argv)
    if args.cmd == "run":
        do_run()
    elif args.cmd == "capture":
        do_capture()
    elif args.cmd == "rollup":
        do_rollup(args.day)
    elif args.cmd == "prune":
        do_prune()
    return 0


if __name__ == "__main__":
    sys.exit(main())
