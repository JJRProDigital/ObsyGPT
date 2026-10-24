#!/bin/sh
set -e

# Xvfb display for Chromium (headed, so the one-time Google sign-in works over noVNC).
rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 1440x900x24 -nolisten tcp &
export DISPLAY=:99

# Chromium exits silently if launched before the X server accepts connections.
i=0
until xset -display :99 q >/dev/null 2>&1 || [ $i -ge 50 ]; do i=$((i + 1)); sleep 0.2; done

# Container restarts change the hostname, so the profile's SingletonLock always points
# to a stale owner ("another computer"). No Chromium runs in this container yet: safe to clear.
rm -f "${FLOW_USER_DATA_DIR}"/SingletonLock "${FLOW_USER_DATA_DIR}"/SingletonCookie "${FLOW_USER_DATA_DIR}"/SingletonSocket

fluxbox >/dev/null 2>&1 &

x11vnc -display :99 -forever -nopw -shared -quiet &

# websockify's --web serves a directory listing at /; add a redirect so opening
# the port lands straight on the noVNC client (auto-connect, scale to window).
cat > /usr/share/novnc/index.html <<'EOF'
<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0; url=vnc.html?autoconnect=1&amp;resize=scale"></head><body></body></html>
EOF

websockify --web /usr/share/novnc "${NOVNC_PORT}" localhost:5900 >/dev/null 2>&1 &

# Open Chromium right away with the exact flags the MCP expects (CDP port +
# persistent profile): ensureChrome() sees the CDP port alive and reuses this
# instance instead of spawning a new one. Visible over noVNC for the sign-in.
"${FLOW_CHROME_PATH:-/usr/bin/chromium}" \
  "--remote-debugging-port=${FLOW_CDP_PORT}" \
  "--user-data-dir=${FLOW_USER_DATA_DIR}" \
  --no-first-run \
  --no-default-browser-check \
  --disable-features=DeviceBoundSessions \
  ${FLOW_CHROME_NO_SANDBOX:+--no-sandbox} \
  https://flow.google.com/ > /tmp/chrome.log 2>&1 &
echo $! > /tmp/chromium.pid

exec node bridge.js
