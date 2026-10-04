# WhatsApp-Style Chat Notifications & Comprehensive Emoji Keyboard Design

## 1. Overview
Integrate a complete WhatsApp-like communication experience across the entire LAN application suite:
1. **Full WhatsApp-Style Emoji Keyboard:** A comprehensive, searchable, categorized Unicode emoji panel integrated into the chat input bar (for message composition) and connected to message reactions. 100% offline, zero external CDN dependencies.
2. **Global WhatsApp Notification Suite:** A unified real-time notification engine operating across all views (`/`, `/chat`, `/dm`, `/uploads`, `/watch`). Features synthesized WhatsApp audio chimes via Web Audio API, animated in-app floating banner toasts with quick navigation, desktop push notifications for background tabs, and dynamic tab title unread badges.

---

## 2. Requirements & Goals

### 2.1 Full Emoji Picker
* **Categorized Unicode Library:** Complete standard emoji catalogue (~1,500 emojis) categorized into:
  - Smileys & Emotion
  - People & Body
  - Animals & Nature
  - Food & Drink
  - Travel & Places
  - Activities & Sports
  - Objects
  - Symbols
  - Flags
* **Instant Search:** Keyword indexing for fast, real-time filtering as the user types (e.g. "fire", "heart", "smile", "cat", "car").
* **Recently Used:** LocalStorage-backed recent emojis row for fast access to favorite emojis.
* **Dual Operation Modes:**
  1. *Input Composition Mode:* Clicking an emoji button (😊) beside the message input opens the picker; selecting an emoji inserts it directly at the cursor location inside `messageInput` without losing typing focus.
  2. *Reaction Mode:* Replaces the limited static reaction list with the full searchable emoji keyboard when adding reactions to messages.
* **Responsive & Accessible:** Closes on click outside or `Escape` key; responsive popup positioning on desktop and mobile viewports.

### 2.2 WhatsApp-Style Notification Suite
* **Web Audio Chime:**
  - Synthesizes the authentic two-tone gentle acoustic incoming chime using browser `AudioContext`.
  - Zero external MP3/WAV audio files needed — no network latency, no broken paths, works offline on isolated LANs.
  - Automatically activates on the first user interaction to comply with browser autoplay policies.
  - Mute setting supported.
* **In-App Floating Toast / Banner:**
  - Appears at the top of the viewport when a new message or DM arrives while the user is viewing another channel, scrolled up, or in another section (e.g., file manager or watch room).
  - Displays sender avatar/initials, channel tag (`[Public Chat]` or `[Direct Message]`), and message preview.
  - Clicking the toast immediately focuses or navigates to that conversation.
  - Auto-dismisses after 4.5 seconds with visual progress indicator.
* **Browser Desktop Notifications:**
  - Dispatches native `Notification` when the browser tab is minimized or in the background.
  - Channel-aware headers (`[DM] Alice` or `[Chat] Bob`) with previews.
  - Clicking the notification focuses the window and navigates to the relevant conversation.
* **Dynamic Tab Title Counter:**
  - Formats browser tab title as `(N) LAN Chat` or `(N) DM - Partner` whenever there are unread messages.
  - Clears immediately when the user views the conversation.

---

## 3. Architecture & Data Flow

### 3.1 Modular File Structure
```
lan_1/
├── static/
│   ├── js/
│   │   ├── emoji-picker.js       # Complete categorized Unicode dataset & UI component
│   │   └── notifications.js      # Web Audio chime, toast banners, desktop alerts, unread tracking
│   └── css/
│       ├── emoji-picker.css      # WhatsApp-style styles for picker, category bar, search
│       └── notifications.css     # Styling for top banner toasts, badges, and animations
├── templates/
│   ├── index.html                # Global notifications script inclusion
│   ├── chat.html                 # Emoji button in input bar + notifications integration
│   ├── dm.html                   # Emoji button in DM input + notifications integration
│   ├── uploads.html              # Global notifications script inclusion
│   └── watch.html                # Global notifications script inclusion
└── app.py                        # (No backend changes required; Socket.IO events already emit full payload)
```

### 3.2 Notification Suppression & Focus Rules
To avoid alert fatigue and mimic WhatsApp's native desktop experience:
1. **Self-Message Suppression:** Never notify or chime for messages sent by the logged-in user.
2. **Active View Suppression:**
   - On `/chat`: If the window is focused and the user is scrolled near the bottom of public chat, do **not** trigger audio or banner toast for public chat messages.
   - On `/dm/<id>`: If the window is focused and active with partner Alice, do **not** trigger alerts for Alice's incoming messages.
3. **Alert Matrix:**
   - **Tab in Background / Minimized:** Audio chime + Browser Desktop Notification + Document title counter.
   - **Tab Focused, but in different channel / scrolled up:** Audio chime + In-app floating toast banner + Document title counter.
   - **Tab Focused in active view:** Silent delivery, message rendered directly in chat view.

---

## 4. Component Details

### 4.1 `static/js/emoji-picker.js`
* Self-contained JavaScript class `EmojiPicker`.
* Exposes:
  - `init({ container, onSelect, triggerBtn })`
  - `open(anchorElement, mode)`
  - `close()`
* Maintains `recentEmojis` in `localStorage.getItem('recent_emojis')`.
* Efficient DOM rendering with category virtual tabs to keep memory usage low and rendering instant.

### 4.2 `static/js/notifications.js`
* Self-contained JavaScript singleton `LANNotifications`.
* Exposes:
  - `init({ socket, currentUser, activeChannel, activePartner })`
  - `playChime()`: Web Audio API oscillator synthesis.
  - `showToast({ title, sender, body, url, onClick })`
  - `showDesktopNotification({ title, body, onClick })`
  - `updateTitle(unreadCount)`
  - `markChannelAsRead(channel)`

---

## 5. Verification & Testing Plan

### 5.1 Emoji Picker Verification
1. **Input Composition:**
   - Open `/chat`, click 😊 icon in input bar.
   - Select categories (Smileys, Food, Animals, Objects, Flags) — verify smooth scrolling and category jumping.
   - Type in search input (e.g. "laugh", "heart", "pizza", "car") — verify instant filtered results.
   - Click an emoji — verify it inserts at the textarea's current cursor position and preserves focus.
2. **Reactions Mode:**
   - Click reaction button on a message — verify full emoji picker opens in reaction mode.
   - Select emoji — verify reaction event is sent and displayed beneath the message.
3. **DM Support:**
   - Open `/dm/<conversation_id>` — verify identical functionality in the DM textarea.

### 5.2 Notification Verification
1. **Background Alerts:**
   - Minimize or switch tabs away from the app.
   - Send a public message from another client — verify audio chime plays, browser system notification appears, and tab title shows `(1) LAN Chat`.
   - Click system notification — verify tab focuses and navigates to `/chat`.
2. **In-App Toast:**
   - Stay on `/uploads` or `/watch`.
   - Send a message from another client — verify audio chime plays and in-app WhatsApp toast banner slides in at top with message preview.
   - Click toast banner — verify seamless navigation to the conversation.
3. **Suppression Check:**
   - With `/chat` active and focused, receive a message — verify no in-app toast or audio chime plays (only direct message render).
