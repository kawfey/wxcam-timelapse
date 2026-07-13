# web/ — rolling timelapse viewer (planned)

Client-side viewer (`index.html` + `viewer.js` + `styles.css`, to be built):
fetches `/frames?cam=&hours=n&max=<target>` (an evenly-subsampled list of stored
JPEG URLs + timestamps) and cycles an `<img>` at a playback fps derived from the
speed multiplier — so changing window/speed/start is instant, no re-encode.
Controls: play/pause, speed, window `n`, current-frame timestamp. Also shows the
live/last still. The exporter (server-side ffmpeg) comes later. See ../docs/plan.md.
