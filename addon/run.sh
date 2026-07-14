#!/usr/bin/with-contenv bashio
# Read add-on options -> export as WXCAM_* env vars -> launch the single uvicorn
# process, which both captures (in-process scheduler) and serves the viewer.
set -e

export WXCAM_INTERVAL_S="$(bashio::config 'interval_s')"
export WXCAM_RETAIN_HOURS="$(bashio::config 'retain_hours')"
export WXCAM_RETAIN_DAYS="$(bashio::config 'retain_days')"
export WXCAM_TIMEZONE="$(bashio::config 'timezone')"
export WXCAM_DATA_DIR="$(bashio::config 'data_dir')"
export WXCAM_RUN_SCHEDULER=1

mkdir -p "${WXCAM_DATA_DIR}"

bashio::log.info "wxcam-timelapse: capture + viewer on :8848"
bashio::log.info "  interval=${WXCAM_INTERVAL_S}s retain=${WXCAM_RETAIN_HOURS}h/${WXCAM_RETAIN_DAYS}d tz=${WXCAM_TIMEZONE}"
bashio::log.info "  data_dir=${WXCAM_DATA_DIR} (shared via HA /media)"

cd /app
exec /opt/venv/bin/uvicorn timelapse.api:app --host 0.0.0.0 --port 8848
