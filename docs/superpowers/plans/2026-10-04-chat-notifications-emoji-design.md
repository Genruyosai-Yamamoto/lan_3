# Chat Notifications (WhatsApp-like) + Full Emoji Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add WhatsApp-like notifications (browser notifications + dynamic title with unread counts) and expand emoji picker to 78 emojis in public chat and DMs.

**Architecture:** Client-side only changes. Track focus (window + active conversation), maintain unread counts, update document title, request Notification permission on first gesture, fire system notifications on qualifying new messages. Replace COMMON_EMOJIS arrays in chat.html and dm.html with expanded set.

**Tech Stack:** Vanilla JavaScript (ES5 compatible style as existing), HTML/CSS, Flask-SocketIO (existing events used as-is), Browser Notification API.

## Global Constraints
- No backend changes required; must use existing Socket.IO events (new_message, new_private_message, reaction events)
- Do not break existing reaction flow, message rendering, encryption flow in DM
- Request Notification permission only on first user interaction
- Graceful degradation if Notification API unavailable (no errors)
- Changes isolated to templates/chat.html and templates/dm.html only (client-side)
- Maintain existing code style and structure

---

### Task 1: Chat - Focus tracking, unread state, title updates, notifications, expanded emoji

**Files:**
- Modify: `templates/chat.html`

**Interfaces:**
- Consumes: existing globals `userName`, `socket`, `appendMessage`, `updateCount`, `escapeHtml`, `toggleReaction`, `closeEmojiPicker`
- Produces: internal client state `windowFocused`, `unreadPublic`, `baseTitle`, `notifyPermissionRequested`, helpers `updateTitle()`, `maybeNotify()`

- [ ] **Step 1: Write the failing test (smoke check via node/jshint not applicable; verify via mental check)**

Validate structure expectations.

- [ ] **Step 2: Add focus/unread state and title management**

Add after userName setup (near top after `const userName = ...` or before socket handlers). Insert:
```javascript
// Notifications & focus state
const baseTitleChat = document.title || 'Team Chat';
let windowFocused = true;
let unreadPublic = 0;
let notifyPermissionRequested = false;

function updateTitleChat() {
  if (unreadPublic > 0) {
    document.title = '(' + unreadPublic + ') ' + baseTitleChat;
  } else {
    document.title = baseTitleChat;
  }
}

function requestNotifyPermission() {
  if (notifyPermissionRequested) return;
  notifyPermissionRequested = true;
  if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
    try {
      Notification.requestPermission().catch(function(){});
    } catch (e) {}
  }
}

// Track focus
window.addEventListener('focus', function() {
  windowFocused = true;
  unreadPublic = 0;
  updateTitleChat();
});
window.addEventListener('blur', function() {
  windowFocused = false;
});
document.addEventListener('visibilitychange', function() {
  windowFocused = document.visibilityState === 'visible';
  if (windowFocused) {
    unreadPublic = 0;
    updateTitleChat();
  }
});

// Request permission on first interaction
['click','keydown','touchstart'].forEach(function(evt) {
  document.addEventListener(evt, requestNotifyPermission, { once: true, passive: true });
});
```

- [ ] **Step 3: Replace emoji set with expanded 78**

Replace `const COMMON_EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🎉', '🔥', '👏'];` with:
```javascript
const COMMON_EMOJIS = ['😀','😁','😂','🤣','😊','😉','😍','😘','🤔','🤨','😐','😔','😢','😭','😠','🤪','😴','🤢','😞','👍','👎','👏','🙌','🙏','👐','✌️','❤️','🧡','💛','💚','💙','💜','💖','💔','🔥','✨','⭐','💫','💯','🎉','🎊','⚠️','🚫','✅','❌','🚀','💬','💭','👀','👇','👆','🎵','🔔','💻','💡','⚙️','😆','😌','😏','🧐','🌈','🍕','🍔','🍨','🐶','🐱','🦄','🐉','🚗','✈️','🚢','🚆','☀️','🌙','☁️','⚡','❄️','☂️'];
```

- [ ] **Step 4: Add notification helper**

Add before socket handlers:
```javascript
function maybeNotifyChat(data) {
  if (typeof Notification === 'undefined') return;
  // Don't notify if focused (or if it's our own message? check sender)
  if (windowFocused) return;
  // Ignore self
  if (data && data.user && userName && data.user === userName) return;
  var title = '[Chat] ' + (data.user || 'Anonymous');
  var body = (data.content || '');
  if (data.type === 'audio') {
    body = '🎤 Voice Message';
  } else if (typeof body === 'string' && body.length > 80) {
    body = body.substring(0, 77) + '...';
  }
  try {
    new Notification(title, { body: body });
  } catch (e) {}
}
```

- [ ] **Step 5: Update new_message handler to track unread + notify**

Modify `socket.on('new_message', ...)` to increment unread when not focused (and not self). Also call maybeNotifyChat. Keep existing appendMessage logic intact.

Replace/extend inside the handler:
```javascript
socket.on('new_message', (data) => {
  appendMessage({...});
  updateCount();
  if (!windowFocused && (!data.user || data.user !== userName)) {
    unreadPublic++;
    updateTitleChat();
    maybeNotifyChat(data);
  }
});
```

- [ ] **Step 6: Verify JavaScript syntax (basic)**

Quick sanity: no syntax errors introduced. Ensure braces balanced.

- [ ] **Step 7: Commit**

```bash
git add templates/chat.html
git commit -m "feat(chat): add WhatsApp-like notifications + dynamic title + expanded emoji picker (78)"
```

---

### Task 2: DM - Focus tracking, unread per conversation, title updates, notifications, expanded emoji

**Files:**
- Modify: `templates/dm.html`

**Interfaces:**
- Consumes: existing `userName`, `partnerName`, `sharedKey`, `decryptMessage`, `appendMessage`, etc.
- Produces: `windowFocusedDM`, `unreadDMByPartner`, `baseTitleDM`, helpers `updateTitleDM()`, `maybeNotifyDM()`

- [ ] **Step 1: Add focus/unread state and title management**

Add after userName/partnerName setup:
```javascript
const baseTitleDM = document.title || 'Direct Chat';
let windowFocusedDM = true;
let unreadDMByPartner = {};
let notifyPermissionRequestedDM = false;

function updateTitleDM() {
  var total = 0;
  for (var k in unreadDMByPartner) {
    if (unreadDMByPartner.hasOwnProperty(k)) total += unreadDMByPartner[k];
  }
  if (total > 0) {
    document.title = '(' + total + ') ' + baseTitleDM;
  } else {
    document.title = baseTitleDM;
  }
}

function requestNotifyPermissionDM() {
  if (notifyPermissionRequestedDM) return;
  notifyPermissionRequestedDM = true;
  if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
    try { Notification.requestPermission().catch(function(){}); } catch(e){}
  }
}

window.addEventListener('focus', function() {
  windowFocusedDM = true;
  // Clear unread for active partner
  if (partnerName) unreadDMByPartner[partnerName] = 0;
  updateTitleDM();
});
window.addEventListener('blur', function() {
  windowFocusedDM = false;
});
document.addEventListener('visibilitychange', function() {
  windowFocusedDM = document.visibilityState === 'visible';
  if (windowFocusedDM && partnerName) {
    unreadDMByPartner[partnerName] = 0;
    updateTitleDM();
  }
});
['click','keydown','touchstart'].forEach(function(evt) {
  document.addEventListener(evt, requestNotifyPermissionDM, { once: true, passive: true });
});
```

- [ ] **Step 2: Replace emoji set with expanded 78**

Replace COMMON_EMOJIS (the long Unicode string form) with:
```javascript
const COMMON_EMOJIS = ['😀','😁','😂','🤣','😊','😉','😍','😘','🤔','🤨','😐','😔','😢','😭','😠','🤪','😴','🤢','😞','👍','👎','👏','🙌','🙏','👐','✌️','❤️','🧡','💛','💚','💙','💜','💖','💔','🔥','✨','⭐','💫','💯','🎉','🎊','⚠️','🚫','✅','❌','🚀','💬','💭','👀','👇','👆','🎵','🔔','💻','💡','⚙️','😆','😌','😏','🧐','🌈','🍕','🍔','🍨','🐶','🐱','🦄','🐉','🚗','✈️','🚢','🚆','☀️','🌙','☁️','⚡','❄️','☂️'];
```

- [ ] **Step 3: Add DM notification helper**

Add before socket handlers. Handle decryption preview if possible (mirror existing appendMessage logic lightly).
```javascript
async function maybeNotifyDM(data) {
  if (typeof Notification === 'undefined') return;
  if (windowFocusedDM && partnerName && data.sender === partnerName) return; // don't notify for active focused convo
  if (windowFocusedDM) return; // general focus
  if (data.sender === userName) return; // ignore self
  var title = '[DM] ' + (data.sender || 'Anonymous');
  var body = (data.content || '');
  if (data.type === 'audio') {
    body = '🎤 Voice Message';
  } else if (body && body.startsWith('enc:') && sharedKey) {
    try {
      body = await decryptMessage(body, sharedKey);
    } catch (e) {}
  }
  if (typeof body === 'string' && body.length > 80) {
    body = body.substring(0, 77) + '...';
  }
  try { new Notification(title, { body: body }); } catch(e){}
}
```

- [ ] **Step 4: Update new_private_message handler**

After appending and updating count, compute if qualifies: if not focused OR (focused but viewing different partner)? Per (d): hybrid - if focused AND currently open conversation (partner matches), don't count/notify. If focused but different partner, still count? Title shows total unread; notifications fire when not focused. But also handle focused case: increment unread for that partner if it's not the active one.

Modify handler:
```javascript
socket.on('new_private_message', async (data) => {
  // ... existing decryption/append ...
  updateCount();
  // determine
  var isActive = partnerName && data.sender === partnerName && windowFocusedDM;
  if (isActive) {
    // viewing active convo and focused - clear it
    if (partnerName) unreadDMByPartner[partnerName] = 0;
    updateTitleDM();
    return;
  }
  // Not the active focused conversation
  if (!isActive) {
    if (data.sender !== userName) {
      if (!unreadDMByPartner[data.sender]) unreadDMByPartner[data.sender] = 0;
      unreadDMByPartner[data.sender]++;
      updateTitleDM();
      maybeNotifyDM(data);
    }
  }
});
```

Note: `maybeNotifyDM` also checks focus; call is fine.

- [ ] **Step 5: Clear unread on partner change / focus already handled**

Existing code sets partnerName from template; focus handlers clear active. Also when user clicks another DM (navigates), page reloads - state resets per page; fine.

- [ ] **Step 6: Verify basic syntax**

No syntax errors.

- [ ] **Step 7: Commit**

```bash
git add templates/dm.html
git commit -m "feat(dm): add WhatsApp-like notifications + dynamic title + expanded emoji picker (78)"
```

---

### Task 3: Manual smoke test

**Files:**
- None (verification)

**Interfaces:**
- Consumes: both modified templates
- Produces: verification notes

- [ ] **Step 1: Start app and test chat notifications (if possible)**

Launch server (Flask dev or existing). Open chat in one tab, another message from different user while tab hidden - title updates, notification may appear if permitted.

- [ ] **Step 2: Test DM notifications**

Open DM with A, receive message from B while focused on A's DM tab? Or switch tabs - behavior matches spec.

- [ ] **Step 3: Test emoji picker**

Click reaction on message, picker shows 78 emojis, selecting one adds reaction (existing flow works).

- [ ] **Step 4: Commit test notes (optional)**

```bash
git add -A 2>/dev/null || true
git commit -m "test: manual smoke test for notifications + emoji picker" || true
```

