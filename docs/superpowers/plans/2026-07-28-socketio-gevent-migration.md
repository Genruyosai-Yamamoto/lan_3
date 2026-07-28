# Socket.IO Gevent Migration & Client Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch Flask-SocketIO from threading to gevent async mode and extract duplicated Socket.IO client boilerplate into a shared `static/socket.js` module.

**Architecture:** Two independent changes: (1) server-side gevent migration via `monkey.patch_all()` + `async_mode="gevent"`, (2) client-side extraction of common connection lifecycle (init, connect, disconnect, heartbeat, online_users, username_taken) into `static/socket.js`. Each HTML template strips ~50 lines of duplicate socket code and replaces it with the shared module plus page-specific callbacks.

**Tech Stack:** Python 3.8+, Flask 3.1, Flask-SocketIO 5.5, gevent 24.11, gevent-websocket 0.10, Socket.IO client v4.7.5

## Global Constraints

- `monkey.patch_all()` must be the first two lines of `app.py` (before any other import)
- `socket.js` must load after `socket.io.min.js` (depends on global `io`)
- `window.currentUsername` is the shared username variable — socket.js reads/writes it, templates set it at init, callbacks reference it
- All 30+ page-specific Socket.IO event handlers must remain untouched (file_update, new_message, watch_sync, call_user, ice_candidate, etc.)
- gevent and gevent-websocket are already installed in the venv — only `requirements.txt` needs updating

---

### Task 1: Server — gevent migration

**Files:**
- Modify: `app.py:1-25`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nothing
- Produces: `socketio` instance now runs on gevent greenlets instead of OS threads

- [ ] **Step 1: Add monkey.patch_all() and change async_mode in app.py**

Insert at the very top of `app.py` (before line 1 / the existing imports):

```python
from gevent import monkey
monkey.patch_all()
```

Change line 24 from:
```python
    async_mode="threading"
```
to:
```python
    async_mode="gevent"
```

- [ ] **Step 2: Update requirements.txt**

Append to `requirements.txt`:
```
gevent>=24.11.1
gevent-websocket>=0.10.1
Flask-SocketIO>=5.5.1
Flask-SQLAlchemy>=3.1.1
```

- [ ] **Step 3: Commit**

```bash
git add app.py requirements.txt
git commit -m "server: migrate Flask-SocketIO from threading to gevent async mode"
```

---

### Task 2: Create static/socket.js

**Files:**
- Create: `static/socket.js`

**Interfaces:**
- Exports (all on `window`): `socket`, `currentUsername`, `updateConnectionStatus(connected)`, `__onConnectCallbacks`
- Consumes: global `io` from `socket.io.min.js`, `sessionStorage['fs_username']`

- [ ] **Step 1: Create static/socket.js**

```javascript
// Shared Socket.IO connection module — loads after socket.io.min.js

window.currentUsername = sessionStorage.getItem('fs_username') || '';
window.__onConnectCallbacks = [];

window.socket = io({
    transports: ['polling', 'websocket'],
    upgrade: true,
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000
});

window.updateConnectionStatus = function (connected) {
    var el = document.getElementById('connectionStatus');
    if (!el) return;
    if (connected) {
        el.innerHTML = '<span class="status-dot" style="position:static;background:var(--success);"></span> Live';
        el.className = 'badge badge-success';
        el.style.background = '';
        el.style.color = '';
    } else {
        el.innerHTML = '<span class="status-dot" style="position:static;background:var(--danger);"></span> Offline';
        el.className = 'badge';
        el.style.background = '#fee2e2';
        el.style.color = '#991b1b';
    }
};

var socket = window.socket;

socket.on('connect', function () {
    window.updateConnectionStatus(true);
    socket.emit('user_online', { name: window.currentUsername });
    for (var i = 0; i < window.__onConnectCallbacks.length; i++) {
        window.__onConnectCallbacks[i]();
    }
});

socket.on('disconnect', function (reason) {
    window.updateConnectionStatus(false);
    console.log('Socket disconnected:', reason);
});

socket.on('connect_error', function (err) {
    console.error('Socket connect error:', err.message);
});

socket.on('username_taken', function (data) {
    var newName = prompt(
        '"' + data.username + '" is already in use by another session.\nPlease choose a different name:',
        'Anonymous'
    );
    if (newName && newName.trim()) {
        window.currentUsername = newName.trim();
        sessionStorage.setItem('fs_username', window.currentUsername);
        document.cookie = 'username=' + encodeURIComponent(window.currentUsername) + '; path=/; max-age=31536000';
        socket.emit('user_online', { name: window.currentUsername });
        for (var i = 0; i < window.__onConnectCallbacks.length; i++) {
            window.__onConnectCallbacks[i]();
        }
    }
});

socket.on('online_users', function (users) {
    if (typeof window.renderOnlineUsers === 'function') {
        window.renderOnlineUsers(users);
    }
});

setInterval(function () {
    if (socket.connected) {
        socket.emit('heartbeat', { name: window.currentUsername });
    }
}, 5000);
```

- [ ] **Step 2: Commit**

```bash
git add static/socket.js
git commit -m "client: add shared Socket.IO connection module"
```

---

### Task 3: Update index.html

**Files:**
- Modify: `templates/index.html:569-700`

**Interfaces:**
- Consumes: `window.socket`, `window.currentUsername`, `window.__onConnectCallbacks`, `window.updateConnectionStatus`, `window.renderOnlineUsers` from socket.js

- [ ] **Step 1: Add socket.js script tag and wire up page-specific code**

After the existing `<script src="{{ url_for('static', filename='socket.io.min.js') }}">` on line 9, add:
```html
<script src="{{ url_for('static', filename='socket.js') }}"></script>
```

In the `<script>` block starting at line 569, **after** the username prompt block (line 573), add:
```javascript
    // Share username with socket.js
    window.currentUsername = userName;
```

**Remove** the following blocks (lines 603-700):

1. Socket.IO init (lines 603-611):
```javascript
    // Socket.IO
    const socket = io({
        transports: ['polling', 'websocket'],
        upgrade: true,
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000
    });
```

2. Connect handler (lines 613-616):
```javascript
    socket.on('connect', () => {
        updateConnectionStatus(true);
        socket.emit('user_online', { name: userName });
    });
```

3. Username taken handler (lines 618-631):
```javascript
    // Handle server rejecting a duplicate username
    socket.on('username_taken', (data) => {
        ...
    });
```

4. Heartbeat (lines 633-638):
```javascript
    // Heartbeat to keep user online status fresh
    setInterval(() => {
        ...
    }, 5000);
```

5. Disconnect handler (lines 640-643):
```javascript
    socket.on('disconnect', (reason) => {
        updateConnectionStatus(false);
        console.log('Socket disconnected:', reason);
    });
```

6. Connect error handler (lines 645-647):
```javascript
    socket.on('connect_error', (err) => {
        console.error('Socket connect error:', err.message);
    });
```

7. Online users handler (lines 649-652) — **replace with `window.renderOnlineUsers`**:
```javascript
    socket.on('online_users', (users) => {
        renderOnlineUsers(users);
        document.getElementById('statUsers').textContent = (users || []).length;
    });
```

8. Update connection status function (lines 686-700):
```javascript
    // UI State
    function updateConnectionStatus(connected) {
        ...
    }
```

**Replace** item 7 with:
```javascript
    window.renderOnlineUsers = function(users) {
        renderOnlineUsers(users);
        document.getElementById('statUsers').textContent = (users || []).length;
    };
```

The page-specific handlers `socket.on('file_update', ...)` and `socket.on('upload_update', ...)` (lines 654-684) must **stay untouched**.

- [ ] **Step 2: Commit**

```bash
git add templates/index.html
git commit -m "client: index.html — use shared socket.js module"
```

---

### Task 4: Update chat.html

**Files:**
- Modify: `templates/chat.html:1056-1171`

**Interfaces:**
- Consumes: `window.socket`, `window.currentUsername`, `window.__onConnectCallbacks`, `window.renderOnlineUsers` from socket.js

- [ ] **Step 1: Add socket.js script tag and wire up page-specific code**

After the existing `<script src="{{ url_for('static', filename='socket.io.min.js') }}">` on line 8, add:
```html
<script src="{{ url_for('static', filename='socket.js') }}"></script>
```

In the `<script>` block, **after** line 1059 (`document.cookie = ...`), add:
```javascript
    window.currentUsername = userName;
```

**Remove** the following blocks:

1. Socket.IO init (lines 1099-1107):
```javascript
    // FIX 2: Socket.IO with reconnection config matching index.html
    const socket = io({
        ...
    });
```

2. Connect handler (lines 1109-1122) — **replace with callback**:
```javascript
    socket.on('connect', () => {
        socket.emit('user_online', { name: userName });
        document.getElementById('chatSubtext').textContent = 'Connected as ' + userName;
        const indicator = document.getElementById('liveIndicator');
        indicator.classList.remove('offline');
        document.getElementById('liveText').textContent = 'Live';
        fetch('/set_username', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: userName })
        }).catch(() => {});
    });
```

3. Username taken handler (lines 1124-1146) — removed (handled by socket.js):
```javascript
    // FIX 4: Handle duplicate username rejection
    socket.on('username_taken', (data) => {
        ...
    });
```

4. Disconnect handler (lines 1148-1155) — **keep page-specific parts inline**:
```javascript
    socket.on('disconnect', (reason) => {
        document.getElementById('chatSubtext').textContent = 'Disconnected';
        const indicator = document.getElementById('liveIndicator');
        indicator.classList.add('offline');
        document.getElementById('liveText').textContent = 'Offline';
        console.log('Socket disconnected:', reason);
    });
```

5. Connect error handler (lines 1157-1159):
```javascript
    socket.on('connect_error', (err) => {
        console.error('Socket connect error:', err.message);
    });
```

6. Heartbeat (lines 1161-1166):
```javascript
    // FIX 6: Heartbeat to keep online status fresh (matches index.html)
    setInterval(() => {
        ...
    }, 5000);
```

7. Online users handler (lines 1168-1171) — **replace with `window.renderOnlineUsers`**:
```javascript
    // FIX 7: Server sends an ARRAY, not a dict. Use Array.isArray check.
    socket.on('online_users', (users) => {
        renderOnlineUsers(users);
    });
```

**Add** after the `window.currentUsername = userName;` line:

```javascript
    // Register connect callback (runs on connect and after username_taken rename)
    __onConnectCallbacks.push(function() {
        fetch('/set_username', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: window.currentUsername })
        }).catch(function() {});
        document.getElementById('chatSubtext').textContent = 'Connected as ' + window.currentUsername;
        var indicator = document.getElementById('liveIndicator');
        indicator.classList.remove('offline');
        document.getElementById('liveText').textContent = 'Live';
    });

    // Register extra rename-time logic (encryption keys, message reload)
    __onConnectCallbacks.push(function() {
        ensureEncryptionKeys(window.currentUsername);
        initMessages();
    });

    // Disconnect handler — page-specific UI updates
    socket.on('disconnect', function(reason) {
        document.getElementById('chatSubtext').textContent = 'Disconnected';
        var indicator = document.getElementById('liveIndicator');
        indicator.classList.add('offline');
        document.getElementById('liveText').textContent = 'Offline';
        console.log('Socket disconnected:', reason);
    });

    window.renderOnlineUsers = function(users) {
        renderOnlineUsers(users);
    };
```

All page-specific handlers below (new_message, message_edited, message_deleted, reaction_added, reaction_removed) must **stay untouched**.

- [ ] **Step 2: Commit**

```bash
git add templates/chat.html
git commit -m "client: chat.html — use shared socket.js module"
```

---

### Task 5: Update dm.html

**Files:**
- Modify: `templates/dm.html:1095-1353`

**Interfaces:**
- Consumes: `window.socket`, `window.currentUsername`, `window.__onConnectCallbacks`, `window.renderOnlineUsers` from socket.js

- [ ] **Step 1: Add socket.js script tag and wire up page-specific code**

After the existing `<script src="{{ url_for('static', filename='socket.io.min.js') }}">` on line 8, add:
```html
<script src="{{ url_for('static', filename='socket.js') }}"></script>
```

In the `<script>` block, **after** line 1099 (`document.cookie = ...`), add:
```javascript
    window.currentUsername = userName;
```

**Remove** the following blocks:

1. Socket.IO init (lines 1268-1276):
```javascript
    // FIX 4: Socket.IO with reconnection config matching other pages
    const socket = io({
        ...
    });
```

2. Connect handler (lines 1278-1299) — **replace with callback**:
```javascript
    socket.on('connect', () => {
        socket.emit('user_online', { name: userName });
        document.getElementById('chatSubtext').textContent = 'Connected as ' + userName;
        const indicator = document.getElementById('liveIndicator');
        if (indicator) {
            indicator.classList.remove('offline');
            document.getElementById('liveText').textContent = 'Live';
        }
        if (partnerName) {
            socket.emit('join_dm', { user1: userName, user2: partnerName });
        }
        fetch('/set_username', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: userName })
        }).catch(() => {});
    });
```

3. Username taken handler (lines 1301-1325) — removed:
```javascript
    // FIX 6: Handle duplicate username rejection
    socket.on('username_taken', (data) => {
        ...
    });
```

4. Disconnect handler (lines 1327-1336) — **keep page-specific parts inline**:
```javascript
    socket.on('disconnect', (reason) => {
        document.getElementById('chatSubtext').textContent = 'Disconnected — reconnecting\u2026';
        const indicator = document.getElementById('liveIndicator');
        if (indicator) {
            indicator.classList.add('offline');
            document.getElementById('liveText').textContent = 'Offline';
        }
        console.log('Socket disconnected:', reason);
    });
```

5. Connect error handler (lines 1338-1340):
```javascript
    socket.on('connect_error', (err) => {
        console.error('Socket connect error:', err.message);
    });
```

6. Heartbeat (lines 1342-1347):
```javascript
    // FIX 8: Heartbeat to keep online status fresh
    setInterval(() => {
        ...
    }, 5000);
```

7. Online users handler (lines 1349-1353) — **replace with `window.renderOnlineUsers`**:
```javascript
    // FIX 9: Server sends an ARRAY not a dict
    socket.on('online_users', (users) => {
        renderOnlineUsers(users);
        renderDMUsers(users);
    });
```

**Add** after the `window.currentUsername = userName;` line:

```javascript
    // Register connect callback
    __onConnectCallbacks.push(function() {
        document.getElementById('chatSubtext').textContent = 'Connected as ' + window.currentUsername;
        var indicator = document.getElementById('liveIndicator');
        if (indicator) {
            indicator.classList.remove('offline');
            document.getElementById('liveText').textContent = 'Live';
        }
        if (partnerName) {
            socket.emit('join_dm', { user1: window.currentUsername, user2: partnerName });
        }
        fetch('/set_username', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: window.currentUsername })
        }).catch(function() {});
    });

    // Register extra rename-time logic
    __onConnectCallbacks.push(function() {
        ensureEncryptionKeys(window.currentUsername);
        initMessages();
    });

    // Disconnect handler — page-specific UI updates
    socket.on('disconnect', function(reason) {
        document.getElementById('chatSubtext').textContent = 'Disconnected — reconnecting\u2026';
        var indicator = document.getElementById('liveIndicator');
        if (indicator) {
            indicator.classList.add('offline');
            document.getElementById('liveText').textContent = 'Offline';
        }
        console.log('Socket disconnected:', reason);
    });

    window.renderOnlineUsers = function(users) {
        renderOnlineUsers(users);
        renderDMUsers(users);
    };
```

All page-specific handlers below (new_private_message, private_message_edited, etc.) must **stay untouched**.

- [ ] **Step 2: Commit**

```bash
git add templates/dm.html
git commit -m "client: dm.html — use shared socket.js module"
```

---

### Task 6: Update watch.html

**Files:**
- Modify: `templates/watch.html:440-483`

**Interfaces:**
- Consumes: `window.socket`, `window.currentUsername`, `window.__onConnectCallbacks`, `window.updateConnectionStatus`, `window.renderOnlineUsers` from socket.js

- [ ] **Step 1: Add socket.js script tag and wire up page-specific code**

After the existing `<script src="{{ url_for('static', filename='socket.io.min.js') }}">` on line 9, add:
```html
<script src="{{ url_for('static', filename='socket.js') }}"></script>
```

In the `<script>` block, **after** line 443 (`document.cookie = ...`), add:
```javascript
    window.currentUsername = userName;
```

**Remove** the following blocks:

1. /set_username fetch (lines 445-450) — **keep only if needed, but the connect callback handles it. Actually keep it — it runs before socket connects, ensuring the session is set immediately.**

Actually, looking at watch.html lines 445-450, this `fetch('/set_username', ...)` runs immediately at page load (before socket connects). It's not part of the socket init — it's a one-time session sync. **Keep it.**

2. Socket.IO init (lines 452-460):
```javascript
    // Socket.IO
    const socket = io({
        ...
    });
```

3. Connect handler (lines 462-466):
```javascript
    socket.on('connect', () => {
        updateConnectionStatus(true);
        socket.emit('user_online', { name: userName });
        socket.emit('get_watch_parties');
    });
```

4. Username taken handler (lines 468-476):
```javascript
    socket.on('username_taken', (data) => {
        ...
    });
```

5. Heartbeat (lines 478-480):
```javascript
    setInterval(() => {
        if (socket.connected) socket.emit('heartbeat', { name: userName });
    }, 5000);
```

6. Disconnect handler (line 482):
```javascript
    socket.on('disconnect', () => updateConnectionStatus(false));
```

7. Online users handler (line 483):
```javascript
    socket.on('online_users', (users) => renderOnlineUsers(users));
```

**Add** after the `window.currentUsername = userName;` line:

```javascript
    // Register connect callback
    __onConnectCallbacks.push(function() {
        socket.emit('get_watch_parties');
    });

    window.renderOnlineUsers = function(users) {
        renderOnlineUsers(users);
    };
```

All page-specific handlers below (watch_parties_updated, watch_party_created, watch_error, etc.) must **stay untouched**.

- [ ] **Step 2: Commit**

```bash
git add templates/watch.html
git commit -m "client: watch.html — use shared socket.js module"
```

---

### Task 7: Update watch_room.html

**Files:**
- Modify: `templates/watch_room.html:499-554`

**Interfaces:**
- Consumes: `window.socket`, `window.currentUsername`, `window.__onConnectCallbacks` from socket.js

- [ ] **Step 1: Add socket.js script tag and wire up page-specific code**

After the existing `<script src="{{ url_for('static', filename='socket.io.min.js') }}">` on line 9, add:
```html
<script src="{{ url_for('static', filename='socket.js') }}"></script>
```

In the `<script>` block, **after** line 507 (`document.cookie = ...`), add:
```javascript
    window.currentUsername = userName;
```

**Remove** the following blocks:

1. Socket.IO init (lines 528-536):
```javascript
    // ===== Socket.IO =====
    const socket = io({
        ...
    });
```

2. Connect handler (lines 542-545):
```javascript
    socket.on('connect', () => {
        socket.emit('user_online', { name: userName });
        socket.emit('join_watch_party', { party_id: PARTY_ID });
    });
```

3. Disconnect handler (lines 547-549) — **keep page-specific parts inline**:
```javascript
    socket.on('disconnect', () => {
        showToast('Disconnected — trying to reconnect...', 'error');
    });
```

4. Reconnect handler (lines 551-554) — **keep page-specific parts inline**:
```javascript
    socket.on('reconnect', () => {
        socket.emit('join_watch_party', { party_id: PARTY_ID });
        showToast('Reconnected!', 'success');
    });
```

Note: watch_room.html does NOT have: heartbeat, username_taken handler, connect_error handler, online_users handler, or updateConnectionStatus function. These are all defaults that socket.js provides. The `updateConnectionStatus` call from socket.js will be a no-op since there's no `#connectionStatus` element — this is fine.

**Add** after the `window.currentUsername = userName;` line:

```javascript
    // Register connect callback
    __onConnectCallbacks.push(function() {
        socket.emit('join_watch_party', { party_id: PARTY_ID });
    });

    // Disconnect — page-specific toast
    socket.on('disconnect', function() {
        showToast('Disconnected — trying to reconnect...', 'error');
    });

    // Reconnect — rejoin party and show toast
    socket.on('reconnect', function() {
        socket.emit('join_watch_party', { party_id: PARTY_ID });
        showToast('Reconnected!', 'success');
    });
```

All page-specific handlers below (watch_party_joined, watch_viewer_update, watch_sync, etc.) must **stay untouched**.

- [ ] **Step 2: Commit**

```bash
git add templates/watch_room.html
git commit -m "client: watch_room.html — use shared socket.js module"
```

---

### Task 8: Integration test

**Files:** none — manual verification

- [ ] **Step 1: Start the server**

```bash
python app.py
```
Expected: server starts on port 5000 with HTTPS, no import errors. The `monkey.patch_all()` should not cause any issues with existing imports.

- [ ] **Step 2: Open dashboard (index.html)**

Navigate to `https://localhost:5000`. Expected:
- Socket.IO connects, sidebar shows "Live" status
- Online users sidebar populates when other tabs connect
- File uploads work, file_update events fire

- [ ] **Step 3: Open group chat (chat.html)**

Navigate to `https://localhost:5000/chat`. Expected:
- Socket connects, subtext shows "Connected as {name}"
- Live indicator shows "Live"
- Sending messages works, messages appear in real-time across tabs
- Duplicate username test: open second chat tab with same name → prompt appears, new name works

- [ ] **Step 4: Open DM (dm.html)**

Navigate to `https://localhost:5000/dm`. Expected:
- Socket connects, subtext and live indicator update
- E2EE keys load, encryption indicator works
- Sending/receiving DMs works
- WebRTC call initiation works

- [ ] **Step 5: Open Watch Party pages**

Navigate to `https://localhost:5000/watch`. Expected:
- Socket connects, party list renders
- Creating a party redirects to the room

Navigate to the watch room. Expected:
- Socket connects, viewers list updates
- Play/pause/seek sync works (host controls video, viewers follow)

- [ ] **Step 6: Test reconnect behavior**

Stop the server with Ctrl+C, then restart. Expected:
- All open pages detect disconnect
- Pages automatically reconnect when server comes back
- No JavaScript errors in console

- [ ] **Step 7: Verify no threading fallback warning**

Check server logs for any warnings about gevent not being available or falling back to threading.

- [ ] **Step 8: Commit any final fixes**

```bash
git add -A
git commit -m "fix: post-integration-test adjustments"
```
