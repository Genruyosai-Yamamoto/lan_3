# Socket.IO Gevent Migration & Client Module Design

## Problem

The LAN app uses Flask-SocketIO with `async_mode="threading"`, allocating one OS thread per connection — fine for 1–2 users but wasteful and unscalable. The Socket.IO client configuration is duplicated across all 5 HTML templates (~50 lines each), creating inconsistency risk and making connection tuning tedious.

## Solution

Two independent changes:

1. **Server**: Switch Flask-SocketIO from threading mode to gevent async mode.
2. **Client**: Extract the shared Socket.IO connection lifecycle into a single `static/socket.js` module.

## 1. Server: gevent Migration

### Changes

- Add `monkey.patch_all()` as the first two lines of `app.py` (before any other import) — required for gevent to patch Python's threading, socket, and time modules for cooperative multitasking.
- Change `SocketIO(async_mode="threading")` → `SocketIO(async_mode="gevent")` on line 24.
- Add `gevent>=24.11.1`, `gevent-websocket>=0.10.1`, `Flask-SocketIO>=5.5.1`, `Flask-SQLAlchemy` to `requirements.txt`.

### Imports in app.py

```
from gevent import monkey
monkey.patch_all()
# ... existing imports below
```

`monkey.patch_all()` must execute before any stdlib import that touches networking (`threading`, `queue`, `time`, `socket`, `ssl`, etc.). Since these are imported later in the file, placing `monkey.patch_all()` at the very top (after the shebang) is sufficient.

### Rationale

`async_mode="threading"` uses one thread per connection via `simple-websocket`. On LAN with many concurrent users (e.g., a watch party + chat + file uploads), threads pile up. Gevent uses greenlets — lightweight coroutines multiplexed onto a single thread — so thousands of connections share one OS thread. `gevent-websocket` provides the WebSocket handler for gevent's event loop.

### Compatibility

- Flask-SocketIO 5.x supports `async_mode="gevent"` natively.
- `gevent` 24.11.1 is already installed in the venv.
- The existing `socketio.run()` call works unchanged — Flask-SocketIO detects gevent and uses the appropriate WSGI server.
- SSL context (`cert.pem`/`key.pem`) passes through to gevent's WSGI server transparently.

## 2. Client: Shared `static/socket.js` Module

### Purpose

Eliminate the duplicated Socket.IO connection boilerplate from 5 HTML templates. Standardize connection config, heartbeat, reconnect handling, and connection status UI in one place.

### File: `static/socket.js`

A plain JS file (no build step, no module system) that attaches to `window`.

**Exports (all on `window`):**

| Export | Type | Description |
|--------|------|-------------|
| `window.socket` | `SocketIO` instance | The connected socket, `io({...})` result |
| `window.currentUsername` | `String` | The current user's display name — set by template init, maintained by socket.js through renames |
| `window.updateConnectionStatus(connected)` | Function | Unified status indicator update for the sidebar |
| `window.__onConnectCallbacks` | `Array<Function>` | Page-specific handlers fired on `connect` and after `username_taken` rename |

**Handlers owned by `socket.js`:**

| Event | Behavior |
|-------|----------|
| **connect** | Calls `updateConnectionStatus(true)`. Emits `user_online` with `window.currentUsername`. Iterates `__onConnectCallbacks`. |
| **disconnect** | Calls `updateConnectionStatus(false)`. Logs reason. |
| **connect_error** | `console.error` with message. |
| **username_taken** | Prompts for new name. Updates `sessionStorage['fs_username']` + `window.currentUsername` + cookie. Re-emits `user_online`. Re-iterates `__onConnectCallbacks` so page-specific setup re-runs with the new name. |
| **online_users** | Dispatches to `window.renderOnlineUsers(users)` — each page defines its own. |
| **heartbeat** | `setInterval` every 5s emits `heartbeat` with `window.currentUsername`. |

**Username sharing contract:**
- Each template's init sets `window.currentUsername` after its initial prompt, alongside the existing `let userName` local.
- socket.js reads/writes `window.currentUsername` for all emits and the rename handler.
- Page-specific callbacks reference `window.currentUsername` (not the local `userName`) so they work correctly after a rename.

### Template Changes

#### All 5 templates

**Keep in each** (dependency for `socket.js`):
- `<script src="socket.io.min.js">` (unchanged — socket.js depends on global `io`)

**Remove from each** (replaced by `socket.js`):
- `const socket = io({...})` block (13 lines, identically duplicated)
- `socket.on('connect', ...)` handler (8–15 lines each, nearly identical)
- `socket.on('disconnect', ...)` handler (3–6 lines)
- `socket.on('connect_error', ...)` handler (2 lines)
- `socket.on('username_taken', ...)` handler (15–25 lines)
- `setInterval` heartbeat block (5 lines)
- `socket.on('online_users', ...)` handler — reduced to defining `window.renderOnlineUsers`
- `updateConnectionStatus()` function definition (if present — index.html, watch.html)

**Add to each** (after the existing `socket.io.min.js` tag):
```html
<script src="{{ url_for('static', filename='socket.js') }}"></script>
<script>
// Page-specific connect callbacks
__onConnectCallbacks.push(() => { ... });

// Page-specific renderOnlineUsers
window.renderOnlineUsers = (users) => { ... };

// ... remaining page-specific event handlers
</script>
```

#### Page-specific `__onConnectCallbacks`

Each template registers a callback that runs on connect and after username changes. Callbacks use `window.currentUsername` (not the local `userName` variable) to stay correct after rename.

| Template | Callback |
|----------|----------|
| `index.html` | None (connect handler in socket.js already emits `user_online`) |
| `chat.html` | `POST /set_username` with `window.currentUsername`, update `chatSubtext` + live indicator |
| `dm.html` | `emit('join_dm', { user1: window.currentUsername, ... })`, `POST /set_username`, update `chatSubtext` + live indicator |
| `watch.html` | `emit('get_watch_parties')` |
| `watch_room.html` | `emit('join_watch_party', { party_id })` |

#### Page-specific `username_taken` extras

`chat.html` and `dm.html` have extra re-init logic on rename (reloading messages, ensuring encryption keys). These register as additional callbacks:

```javascript
// chat.html extra — runs on connect AND after rename
__onConnectCallbacks.push(() => {
    ensureEncryptionKeys(window.currentUsername);
    initMessages();
});
```

### Connection Config (standardized in `socket.js`)

```javascript
const socket = io({
    transports: ['polling', 'websocket'],
    upgrade: true,
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000
});
```

This matches the current config in every template exactly. No behavioral change.

### Socket.IO Client Library

The existing `static/socket.io.min.js` (Socket.IO v4.7.5, 50KB minified) is already the correct version for Flask-SocketIO 5.x / python-socketio 5.x. No change needed — it stays as-is. `socket.js` loads after it and depends on the global `io` function it provides.

## Files Changed

| File | Change |
|------|--------|
| `app.py` | Add `monkey.patch_all()`, change `async_mode` to `"gevent"` |
| `static/socket.js` | **New file** — shared connection module |
| `templates/index.html` | Strip socket boilerplate, use socket.js |
| `templates/chat.html` | Strip socket boilerplate, use socket.js |
| `templates/dm.html` | Strip socket boilerplate, use socket.js |
| `templates/watch.html` | Strip socket boilerplate, use socket.js |
| `templates/watch_room.html` | Strip socket boilerplate, use socket.js |
| `requirements.txt` | Add gevent, gevent-websocket, Flask-SocketIO, Flask-SQLAlchemy |

## Testing

- Start server: `python app.py` — should start on port 5000 with HTTPS
- Open dashboard, chat, DM, watch pages — all should connect to Socket.IO
- Verify `Online Users` sidebar shows connected users
- Simulate disconnect (stop server, restart) — pages should reconnect automatically
- Duplicate username (open in two tabs with same name) — prompt should appear
- WebRTC calls, file uploads, watch party sync should function unchanged
- Check server logs for no threading-related warnings; greenlet-based serving should be transparent

## Out of Scope

- No authentication system
- No database migration for SQLite schema
- No changes to E2EE, WebRTC, file upload logic
- No conversion to ES modules or build tooling
