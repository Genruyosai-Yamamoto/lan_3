# Offline Loading Fix & UDP Fail-Safe Design

## Problem

Two issues on the LAN file-sharing/media server:

1. **Slow page loads.** All 5 templates pull Google Fonts over the internet via a render-blocking `<link rel="stylesheet">` plus a `<link rel="preconnect">`. When the network is offline (the intended deployment), the browser stalls rendering while those connections time out. Static assets are also served without caching headers, and the server runs with `debug=True`.
2. **No fail-safe channel.** The server has a single point of failure: the HTTPS/Socket.IO (TCP) listener. If it becomes weak or throws SSL errors, there is no independent channel to check server health or discover it.

## Solution

Two independent changes:

1. **Loading:** Self-host the Inter font locally, enable static caching, drop `debug=True`, and eliminate all external URLs from templates.
2. **Fail-safe:** Add a UDP listener on the **same port number** (5000) that serves LAN discovery and health status. A zero-dependency Python CLI (`lan_status.py`) tries TCP first and **flips to UDP** on the same host:port when TCP is weak or throws SSL errors, flipping back once TCP recovers.

Additionally, merge the already-complete `socketio-gevent-migration` branch so socket connections run on greenlets and the duplicated Socket.IO client boilerplate collapses into `static/socket.js`.

## 1. Offline Loading Fix

### Self-host Inter

- Fetch the Inter woff2 files for the weights actually used in the templates (300–700) once during implementation from Google's font CDN. Inter is SIL OFL-licensed, safe to bundle and distribute.
- Store them under `static/fonts/` (e.g. `Inter-latin-400.woff2`, etc.).
- Create `static/fonts.css` with `@font-face` rules for `Inter` plus a system-font fallback stack. The templates already declare `font-family: 'Inter', system-ui, ...` inline, so the `@font-face` name match means no other CSS changes are needed.
- In all 5 templates (`index.html`, `chat.html`, `dm.html`, `watch.html`, `watch_room.html`) replace the two Google Fonts `<link>` tags with:
  ```html
  <link rel="stylesheet" href="{{ url_for('static', filename='fonts.css') }}">
  ```
- Verify with a grep that no `http://` / `https://` references remain in any template.

### Static caching

- Set `app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400` in `app.py` so `socket.io.min.js`, `socket.js`, and `fonts.css` are cached by browsers — repeat loads are served locally without revalidation.

### Drop debug mode

- Change `socketio.run(..., debug=True, ...)` to `debug=False` (both the HTTPS and HTTP-fallback call sites).

## 2. Merge Gevent Migration Branch

- Merge `socketio-gevent-migration` into `main`.
- The working tree on `main` has uncommitted `app.py` comment-removal cleanup. The branch modifies `app.py` (`monkey.patch_all()` at the top, `async_mode="gevent"`). These touch the same file and will conflict. Resolve so the final `app.py` contains the comment cleanup **and** the gevent changes.
- `static/socket.js` and the 5 template refactors arrive via the merge.
- Update `requirements.txt` to list the real dependencies:
  ```
  Flask-SocketIO>=5.5.1
  Flask-SQLAlchemy>=3.1.1
  gevent>=24.11.1
  gevent-websocket>=0.10.1
  ```
- `gevent` (26.7.0) is already installed in the venv; `gevent-websocket` is **not** — install it (gevent async mode needs it for WebSocket upgrades; without it clients fall back to long-polling).

## 3. UDP Fail-Safe Server (Same Port)

### Module: `udp_server.py`

A `LanUdpServer` class.

**Same port number:** TCP and UDP are separate protocols and can share a port number without conflict. The UDP socket binds to the **same port as the HTTPS/Socket.IO server — 5000 by default** (`LAN_UDP_PORT` env overrides). The fail-over is seamless at the address level: same host, same port, different transport.

**True independence:** The listener runs in its own native OS thread (daemon), created with gevent's *original* threading API, and uses the *original* blocking socket API (via `gevent.monkey.get_original`). This ensures the UDP listener keeps answering even if the gevent/TCP serving stalls or the web server fails.

**Protocol** — tiny plaintext datagrams (≤512 bytes, fits one UDP packet), newline-delimited:

| Direction | Message | Reply |
|-----------|---------|-------|
| client → server | `LAN_DISCOVER` | `LAN_HELLO {json}` to the sender |
| client → server | `LAN_PING` | `LAN_PONG {json}` to the sender |
| server → LAN (periodic) | broadcast `LAN_HELLO {json}` every 15s to `255.255.255.255:5000` | passive discovery |

**Payload** (JSON):
```json
{"name": "LAN-Server", "version": "1.0.0", "tcp_port": 5000, "udp_port": 5000, "uptime_sec": 123, "tcp_status": "up"}
```
`version` is a module-level constant in `udp_server.py` (starts at `"1.0.0"`). `uptime_sec` is seconds since the UDP thread started.

**TCP health:** Each response computes `tcp_status` by probing `127.0.0.1:5000` with the original socket and a 1s timeout (`"up"` / `"down"`). When the web server is down, UDP still responds but reports `tcp_status: "down"` — the network can tell the box is alive while the TCP app is not.

**Startup:** Started in `app.py`'s `__main__` block alongside `socketio.run()`. Also runnable standalone (`python udp_server.py`) for testing the fail-over case.

## 4. CLI Client `lan_status.py`

Zero-dependency Python (stdlib `socket` only), runnable from any device on the LAN.

- `python lan_status.py` → broadcast `LAN_DISCOVER` to `255.255.255.255:5000`, listen ~3s, print discovered servers (name, IP, TCP port, `tcp_status`).
- `python lan_status.py <ip>` → **fail-over flow**:
  1. Try TCP first: `GET /api/health` over HTTPS to `<ip>:5000` with a 2s timeout, up to 3 attempts.
  2. On **SSL error** (cert/handshake failure) or **weak TCP** (all attempts timed out) → **flip to UDP**: send `LAN_PING` to `<ip>:5000` and print the UDP health response.
  3. Use the returned `tcp_status` to know when TCP has recovered and flip back to TCP.
- The client listens for UDP responses for 3s (discovery mode) and 2s (ping mode).
- Distinct exit codes/messages for: TCP healthy (0), flipped to UDP (reason: `ssl_error` / `timeout`), UDP unreachable (2).

**New minimal endpoint:** `GET /api/health` in `app.py` returns `{"status": "up", "tcp_port": 5000, "uptime_sec": ...}` so the CLI's TCP probe has a real endpoint to hit.

**Browser limitation (documented):** Browsers cannot send raw UDP. The web UI (chat, DM, watch party, streaming) cannot physically flip to UDP; it keeps its existing Socket.IO polling/websocket reconnect behavior. The UDP fail-over applies to non-browser clients, i.e. `lan_status.py` (and any future native client).

## 5. Files Changed

| File | Change |
|------|--------|
| `static/fonts.css` | **New** — `@font-face` rules for locally-hosted Inter |
| `static/fonts/Inter-*.woff2` | **New** — font binaries fetched once during implementation |
| `udp_server.py` | **New** — `LanUdpServer` (native-thread UDP listener, discovery + health + beacon) |
| `lan_status.py` | **New** — fail-over CLI client (TCP → UDP on SSL error / weak TCP) |
| `app.py` | Merge gevent changes, `debug=False`, `SEND_FILE_MAX_AGE_DEFAULT=86400`, start UDP thread, add `GET /api/health` |
| `templates/index.html` | Replace Google Fonts links with `fonts.css` |
| `templates/chat.html` | Replace Google Fonts links with `fonts.css` |
| `templates/dm.html` | Replace Google Fonts links with `fonts.css` |
| `templates/watch.html` | Replace Google Fonts links with `fonts.css` |
| `templates/watch_room.html` | Replace Google Fonts links with `fonts.css` |
| `requirements.txt` | Add Flask-SocketIO, Flask-SQLAlchemy, gevent, gevent-websocket |
| `static/socket.js` | Arrives via gevent branch merge (shared Socket.IO module) |

## Testing

- **Offline load:** block internet access; pages render instantly; grep confirms zero external URLs in templates.
- **UDP discovery:** `python lan_status.py` finds the server on port 5000.
- **Fail-over (TCP down):** with nothing bound to TCP 5000 (simulate by running `udp_server.py` standalone), the CLI flips to UDP and reports `tcp_status: down`.
- **Fail-over (SSL error):** point the CLI at a cert it can't validate (or corrupt `cert.pem`); confirm it flips to UDP.
- **Recovery:** restore TCP; CLI flips back to TCP.
- **Gevent regression:** multiple tabs/devices connect; chat, DM, watch-party sync, uploads, WebRTC signaling all still work; no threading-fallback warning in server logs.

## Out of Scope

- No UDP transport for the browser web app (platform limitation).
- No UDP chat/message fallback channel.
- No authentication changes.
- No changes to E2EE, WebRTC, or file streaming logic.
