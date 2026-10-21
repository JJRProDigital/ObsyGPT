FROM node:22-slim

ENV DEBIAN_FRONTEND=noninteractive

# Chromium (headed, driven by the MCP over CDP) + a minimal desktop stack:
# Xvfb renders, x11vnc exposes it, noVNC serves it in the browser for the
# one-time Google sign-in. Fonts keep the Flow UI legible.
# Google Chrome (branded, real DBSC/session handling that Google's servers trust) over
# the Debian chromium build, whose sessions get revoked on every restart. Chromium stays
# as fallback binary.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget \
    && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O /tmp/chrome.deb \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm -f /tmp/chrome.deb \
    && apt-get install -y --no-install-recommends \
    xvfb \
    x11-xserver-utils \
    fluxbox \
    x11vnc \
    novnc \
    websockify \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev

COPY src/ ./src/
COPY bridge.js ./bridge.js
COPY entrypoint.sh ./entrypoint.sh

ENV NODE_ENV=production \
    FLOW_CHROME_PATH=/usr/bin/google-chrome \
    FLOW_CHROME_NO_SANDBOX=1 \
    FLOW_CDP_PORT=9222 \
    FLOW_USER_DATA_DIR=/config/flow-profile \
    FLOW_STATE_FILE=/config/flow-profile/state.json \
    FLOW_CONFIG_FILE=/config/flow-profile/config.json \
    FLOW_OUTPUT_DIR=/data/images \
    PORT=8808 \
    NOVNC_PORT=6901

EXPOSE 8808 6901

ENTRYPOINT ["sh", "./entrypoint.sh"]
