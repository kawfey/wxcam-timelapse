# Supervisor passes BUILD_FROM from build.yaml.
ARG BUILD_FROM
FROM ${BUILD_FROM}

# System deps: Python (Debian bookworm = 3.11, meets our >=3.11), ffmpeg for the
# nightly rollup, git to fetch the app.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

# Fetch the application. Editable install keeps the package at /app so the app's
# REPO_ROOT resolves web/ + config/ (config.py derives paths relative to the
# package). Override WXCAM_REF to build from a branch/tag other than main.
ARG WXCAM_REF=main
RUN git clone --depth 1 --branch "${WXCAM_REF}" \
        https://github.com/kawfey/wxcam-timelapse /app \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -e /app

COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
