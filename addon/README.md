# wxcam Timelapse — Home Assistant add-on

Capture webcam stills on a schedule, build daily timelapses, and play them back in
the browser — running as a Supervisor-managed add-on on Home Assistant OS.

- **Viewer + API:** `http://<ha-host>:8848`
- **Storage:** `/media/wxcam-timelapse` (shared with HA's Media panel)
- **Cameras:** MO DNR + 18 KMOV Ford Skycam stills (St. Louis), auto-discovered
  from the app's `config/cameras.csv`.

See [DOCS.md](DOCS.md) for install and configuration. The add-on packages the
[wxcam-timelapse](https://github.com/kawfey/wxcam-timelapse) app; capture + viewer
run as a single `uvicorn` process.
