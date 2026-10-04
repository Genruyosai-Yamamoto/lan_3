# WhatsApp-Style Chat Notifications & Comprehensive Emoji Keyboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a full WhatsApp-like real-time notification suite (Web Audio API sound chime, floating in-app toast banners, desktop push, and dynamic tab title unread badges) and a complete categorized, searchable Unicode emoji keyboard for chat inputs and message reactions across the entire LAN application.

**Architecture:** Client-side modular architecture with zero external CDN dependencies. `notifications.js` and `notifications.css` provide global audio synthesis, presence-aware toast banners, and desktop alerts across all pages (`/`, `/chat`, `/dm`, `/uploads`, `/watch`). `emoji-picker.js` and `emoji-picker.css` encapsulate ~1,500 standard Unicode emojis into 9 WhatsApp categories with real-time keyword search and dual-mode insertion (message textarea and reactions).

**Tech Stack:** JavaScript (ES6+), Web Audio API (`AudioContext`, `OscillatorNode`, `GainNode`), Browser `Notification` API, Socket.IO client, CSS3 Flexbox/Grid animations, Flask / Jinja2 templates.

## Global Constraints
- 100% offline & LAN-ready: Zero external CDN downloads or external media dependencies.
- Non-breaking backend: Reuses existing Socket.IO event schemas (`new_message`, `new_private_message`, `message_reaction`).
- Strict suppression: Never alert for own messages or messages in currently focused conversation.
- Memory efficient: Native Unicode emoji glyphs, virtual category scrolling.

---

### Task 1: Notifications Engine & CSS (`notifications.js` & `notifications.css`)

**Files:**
- Create: `static/css/notifications.css`
- Create: `static/js/notifications.js`
- Test: Manual browser test / test harness in `static/test_notifications.html`

**Interfaces:**
- Produces: `window.LANNotifications` singleton with methods:
  - `init({ socket, currentUser, activeChannel, activePartner })`
  - `playChime()`
  - `showToast({ title, sender, body, url, onClick })`
  - `showDesktopNotification({ title, body, onClick })`
  - `updateTitle(unreadDelta)`
  - `clearUnread()`

- [x] **Step 1: Create `static/css/notifications.css`**
Define styling for the floating in-app toast banner, progress bar, sender avatar, and message preview.
```css
/* Floating in-app WhatsApp notification toast */
.lan-toast-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 10px;
    pointer-events: none;
}
.lan-toast {
    pointer-events: auto;
    width: 320px;
    max-width: 90vw;
    background: var(--surface, #1e293b);
    color: var(--text, #f8fafc);
    border: 1px solid var(--border, rgba(255,255,255,0.1));
    border-radius: 12px;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.3);
    padding: 12px 14px;
    display: flex;
    align-items: flex-start;
    gap: 12px;
    cursor: pointer;
    position: relative;
    overflow: hidden;
    animation: toastSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    transition: transform 0.2s ease, opacity 0.2s ease;
}
.lan-toast:hover {
    transform: translateY(-2px);
    box-shadow: 0 14px 28px -5px rgba(0, 0, 0, 0.5);
}
@keyframes toastSlideIn {
    from { transform: translateX(110%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}
.lan-toast.hiding {
    animation: toastSlideOut 0.25s forwards ease-in;
}
@keyframes toastSlideOut {
    to { transform: translateX(110%); opacity: 0; }
}
.lan-toast-avatar {
    width: 38px;
    height: 38px;
    border-radius: 50%;
    background: linear-gradient(135deg, #25d366, #128c7e);
    color: #fff;
    font-weight: 700;
    font-size: 15px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.lan-toast-content {
    flex: 1;
    min-width: 0;
}
.lan-toast-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 2px;
}
.lan-toast-sender {
    font-weight: 600;
    font-size: 14px;
    color: #25d366;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.lan-toast-tag {
    font-size: 10px;
    text-transform: uppercase;
    background: rgba(255,255,255,0.08);
    padding: 1px 6px;
    border-radius: 4px;
    opacity: 0.7;
}
.lan-toast-body {
    font-size: 13px;
    color: var(--text-muted, #94a3b8);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.lan-toast-progress {
    position: absolute;
    bottom: 0;
    left: 0;
    height: 3px;
    background: #25d366;
    width: 100%;
    animation: toastProgress 4.5s linear forwards;
}
@keyframes toastProgress {
    from { width: 100%; }
    to { width: 0%; }
}
```

- [x] **Step 2: Create `static/js/notifications.js`**
Implement the Web Audio API WhatsApp sound synthesizer, unread title tracking, desktop push, in-app toast manager, and focus suppression.
```javascript
(function(window) {
    'use strict';

    class NotificationManager {
        constructor() {
            this.audioCtx = null;
            this.isMuted = localStorage.getItem('lan_chat_muted') === 'true';
            this.currentUser = null;
            this.activeChannel = null; // 'chat' | 'dm' | null
            this.activePartner = null; // string for DM
            this.unreadCount = 0;
            this.baseTitle = document.title;
            this.isWindowFocused = document.visibilityState === 'visible';
            this.toastContainer = null;

            this._bindEvents();
            this._createToastContainer();
        }

        _bindEvents() {
            window.addEventListener('focus', () => {
                this.isWindowFocused = true;
                this.clearUnread();
            });
            window.addEventListener('blur', () => {
                this.isWindowFocused = false;
            });
            document.addEventListener('visibilitychange', () => {
                this.isWindowFocused = document.visibilityState === 'visible';
                if (this.isWindowFocused) {
                    this.clearUnread();
                }
            });

            // Unlock Web Audio on first gesture
            const unlockAudio = () => {
                if (!this.audioCtx) {
                    const AudioContext = window.AudioContext || window.webkitAudioContext;
                    if (AudioContext) {
                        this.audioCtx = new AudioContext();
                    }
                }
                if (this.audioCtx && this.audioCtx.state === 'suspended') {
                    this.audioCtx.resume();
                }
                window.removeEventListener('click', unlockAudio);
                window.removeEventListener('keydown', unlockAudio);
            };
            window.addEventListener('click', unlockAudio);
            window.addEventListener('keydown', unlockAudio);
        }

        _createToastContainer() {
            if (!document.querySelector('.lan-toast-container')) {
                this.toastContainer = document.createElement('div');
                this.toastContainer.className = 'lan-toast-container';
                document.body.appendChild(this.toastContainer);
            } else {
                this.toastContainer = document.querySelector('.lan-toast-container');
            }
        }

        init({ socket, currentUser, activeChannel, activePartner }) {
            this.currentUser = currentUser || sessionStorage.getItem('fs_username') || 'Anonymous';
            this.activeChannel = activeChannel || null;
            this.activePartner = activePartner || null;

            if (socket) {
                this.attachSocket(socket);
            }
            this.requestDesktopPermission();
        }

        requestDesktopPermission() {
            if ('Notification' in window && Notification.permission === 'default') {
                Notification.requestPermission().catch(() => {});
            }
        }

        attachSocket(socket) {
            socket.on('new_message', (msg) => {
                this.handleIncomingMessage({
                    type: 'chat',
                    sender: msg.user,
                    content: msg.content,
                    messageType: msg.type,
                    id: msg.id
                });
            });

            socket.on('new_private_message', (msg) => {
                this.handleIncomingMessage({
                    type: 'dm',
                    sender: msg.sender,
                    receiver: msg.receiver,
                    content: msg.content,
                    messageType: msg.type,
                    id: msg.id
                });
            });
        }

        handleIncomingMessage({ type, sender, receiver, content, messageType, id }) {
            // Never alert for own message
            if (sender === this.currentUser) return;

            // Check if user is currently active in this conversation
            const isCurrentChatActive = this.isWindowFocused && this.activeChannel === 'chat' && type === 'chat';
            const isCurrentDMActive = this.isWindowFocused && this.activeChannel === 'dm' && type === 'dm' &&
                (this.activePartner === sender || this.activePartner === receiver);

            if (isCurrentChatActive || isCurrentDMActive) {
                // User is actively reading this conversation
                return;
            }

            // Message is unread
            this.unreadCount++;
            this.updateTitle();

            // Play WhatsApp audio chime
            this.playChime();

            let preview = content || '';
            if (messageType === 'audio') {
                preview = '🎤 Voice Message';
            } else if (messageType === 'file') {
                preview = '📁 Attachment';
            }

            const channelTag = type === 'dm' ? `🔒 DM from ${sender}` : `💬 Public Chat: ${sender}`;
            const targetUrl = type === 'dm' ? `/dm` : `/chat`;

            // If window is backgrounded/minimized, send desktop push
            if (!this.isWindowFocused) {
                this.showDesktopNotification({
                    title: channelTag,
                    body: preview,
                    onClick: () => {
                        window.focus();
                        if (window.location.pathname !== targetUrl) {
                            window.location.href = targetUrl;
                        }
                    }
                });
            } else {
                // Window is focused but user is on another page or scrolled up -> show toast banner
                this.showToast({
                    sender: sender,
                    tag: type === 'dm' ? 'Direct Message' : 'Public Chat',
                    body: preview,
                    onClick: () => {
                        if (window.location.pathname !== targetUrl) {
                            window.location.href = targetUrl;
                        }
                    }
                });
            }
        }

        playChime() {
            if (this.isMuted) return;
            try {
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                if (!this.audioCtx && AudioContext) {
                    this.audioCtx = new AudioContext();
                }
                if (!this.audioCtx) return;
                if (this.audioCtx.state === 'suspended') {
                    this.audioCtx.resume();
                }

                const ctx = this.audioCtx;
                const now = ctx.currentTime;

                // WhatsApp signature two-tone acoustic bell
                // Tone 1: 830Hz
                const osc1 = ctx.createOscillator();
                const gain1 = ctx.createGain();
                osc1.type = 'sine';
                osc1.frequency.setValueAtTime(830, now);
                osc1.frequency.exponentialRampToValueAtTime(880, now + 0.08);

                gain1.gain.setValueAtTime(0, now);
                gain1.gain.linearRampToValueAtTime(0.28, now + 0.015);
                gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.22);

                osc1.connect(gain1);
                gain1.connect(ctx.destination);
                osc1.start(now);
                osc1.stop(now + 0.22);

                // Tone 2: 1046Hz (C6) - clean high resolution chime
                const osc2 = ctx.createOscillator();
                const gain2 = ctx.createGain();
                osc2.type = 'sine';
                osc2.frequency.setValueAtTime(1046, now + 0.07);
                osc2.frequency.exponentialRampToValueAtTime(1080, now + 0.28);

                gain2.gain.setValueAtTime(0, now + 0.07);
                gain2.gain.linearRampToValueAtTime(0.35, now + 0.09);
                gain2.gain.exponentialRampToValueAtTime(0.0001, now + 0.45);

                osc2.connect(gain2);
                gain2.connect(ctx.destination);
                osc2.start(now + 0.07);
                osc2.stop(now + 0.45);
            } catch (e) {
                console.warn('Web Audio chime playback failed:', e);
            }
        }

        showToast({ sender, tag, body, onClick }) {
            this._createToastContainer();
            const toast = document.createElement('div');
            toast.className = 'lan-toast';

            const initials = (sender || '?').slice(0, 2).toUpperCase();

            toast.innerHTML = `
                <div class="lan-toast-avatar">${initials}</div>
                <div class="lan-toast-content">
                    <div class="lan-toast-header">
                        <span class="lan-toast-sender">${sender}</span>
                        <span class="lan-toast-tag">${tag}</span>
                    </div>
                    <div class="lan-toast-body">${body}</div>
                </div>
                <div class="lan-toast-progress"></div>
            `;

            toast.addEventListener('click', () => {
                if (typeof onClick === 'function') onClick();
                toast.remove();
            });

            this.toastContainer.appendChild(toast);

            setTimeout(() => {
                toast.classList.add('hiding');
                setTimeout(() => toast.remove(), 250);
            }, 4500);
        }

        showDesktopNotification({ title, body, onClick }) {
            if (!('Notification' in window) || Notification.permission !== 'granted') {
                return;
            }
            try {
                const notif = new Notification(title, {
                    body: body,
                    icon: '/static/favicon.ico',
                    tag: 'lan-chat-message'
                });
                if (typeof onClick === 'function') {
                    notif.onclick = () => {
                        onClick();
                        notif.close();
                    };
                }
            } catch (e) {}
        }

        updateTitle() {
            if (this.unreadCount > 0) {
                document.title = `(${this.unreadCount}) ${this.baseTitle.replace(/^\(\d+\)\s*/, '')}`;
            } else {
                document.title = this.baseTitle.replace(/^\(\d+\)\s*/, '');
            }
        }

        clearUnread() {
            this.unreadCount = 0;
            this.updateTitle();
        }
    }

    window.LANNotifications = new NotificationManager();
})(window);
```

- [x] **Step 3: Commit Notification Engine files**
```bash
git add static/css/notifications.css static/js/notifications.js
git commit -m "feat(notifications): add Web Audio WhatsApp chime, in-app toast, and unread title tracking"
```

---

### Task 2: Comprehensive WhatsApp Emoji Picker (`emoji-picker.js` & `emoji-picker.css`)

**Files:**
- Create: `static/css/emoji-picker.css`
- Create: `static/js/emoji-picker.js`

**Interfaces:**
- Produces: `window.LANEmojiPicker` with methods:
  - `init({ container, onSelect, triggerBtn })`
  - `open(anchorElement, mode, onSelectCallback)`
  - `close()`
  - `insertAtCursor(textarea, emojiChar)`

- [x] **Step 1: Create `static/css/emoji-picker.css`**
WhatsApp-style layout with category tab bar, search input, smooth emoji grid, hover reactions, and scrollable container.
```css
.lan-emoji-picker {
    position: absolute;
    bottom: calc(100% + 8px);
    left: 0;
    width: 340px;
    max-width: calc(100vw - 32px);
    height: 380px;
    background: var(--surface, #1e293b);
    border: 1px solid var(--border, rgba(255, 255, 255, 0.12));
    border-radius: 12px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35);
    display: flex;
    flex-direction: column;
    z-index: 1000;
    overflow: hidden;
    animation: emojiPop 0.15s cubic-bezier(0.16, 1, 0.3, 1);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
@keyframes emojiPop {
    from { opacity: 0; transform: scale(0.95) translateY(4px); }
    to { opacity: 1; transform: scale(1) translateY(0); }
}
.lan-emoji-picker.hidden {
    display: none !important;
}
.lan-emoji-search-box {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.08));
    display: flex;
    align-items: center;
    gap: 6px;
    background: var(--bg-alt, rgba(0, 0, 0, 0.15));
}
.lan-emoji-search-input {
    flex: 1;
    background: var(--bg, #0f172a);
    border: 1px solid var(--border, rgba(255, 255, 255, 0.1));
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    color: var(--text, #f8fafc);
    outline: none;
}
.lan-emoji-search-input:focus {
    border-color: #25d366;
}
.lan-emoji-categories {
    display: flex;
    align-items: center;
    justify-content: space-around;
    padding: 4px 6px;
    border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.08));
    background: var(--surface, #1e293b);
}
.lan-emoji-cat-btn {
    background: none;
    border: none;
    font-size: 16px;
    padding: 4px 6px;
    border-radius: 6px;
    cursor: pointer;
    opacity: 0.6;
    transition: opacity 0.15s, background 0.15s;
}
.lan-emoji-cat-btn:hover,
.lan-emoji-cat-btn.active {
    opacity: 1;
    background: rgba(255, 255, 255, 0.08);
}
.lan-emoji-body {
    flex: 1;
    overflow-y: auto;
    padding: 8px 10px;
}
.lan-emoji-section-title {
    font-size: 11px;
    text-transform: uppercase;
    font-weight: 700;
    color: var(--text-muted, #94a3b8);
    margin: 6px 0 4px 2px;
}
.lan-emoji-grid {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 4px;
}
.lan-emoji-item {
    font-size: 20px;
    height: 34px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    cursor: pointer;
    user-select: none;
    transition: transform 0.1s, background 0.1s;
}
.lan-emoji-item:hover {
    background: rgba(255, 255, 255, 0.12);
    transform: scale(1.2);
}
```

- [x] **Step 2: Create `static/js/emoji-picker.js`**
Pack the comprehensive WhatsApp Unicode emoji library organized into standard categories with search keywords, local storage favorites, cursor insertion, and reaction binding.
```javascript
(function(window) {
    'use strict';

    const EMOJI_DATA = [
        {
            id: 'smileys',
            name: 'Smileys & Emotion',
            icon: '😃',
            emojis: [
                { e: '😀', k: 'grinning face smile happy' },
                { e: '😃', k: 'smiling face with big eyes' },
                { e: '😄', k: 'smiling face with smiling eyes' },
                { e: '😁', k: 'beaming face with smiling eyes grin' },
                { e: '😆', k: 'grinning squinting face laugh' },
                { e: '😅', k: 'grinning face with sweat' },
                { e: '🤣', k: 'rolling on the floor laughing rofl' },
                { e: '😂', k: 'face with tears of joy lol' },
                { e: '🙂', k: 'slightly smiling face' },
                { e: '🙃', k: 'upside-down face sarcasm' },
                { e: '😉', k: 'winking face wink' },
                { e: '😊', k: 'smiling face with smiling eyes blush' },
                { e: '😇', k: 'smiling face with halo angel' },
                { e: '🥰', k: 'smiling face with hearts love' },
                { e: '😍', k: 'smiling face with heart-eyes' },
                { e: '🤩', k: 'star-struck excited' },
                { e: '😘', k: 'face blowing a kiss' },
                { e: '😗', k: 'kissing face' },
                { e: '😚', k: 'kissing face with closed eyes' },
                { e: '😙', k: 'kissing face with smiling eyes' },
                { e: '😋', k: 'face savoring food delicious yum' },
                { e: '😛', k: 'face with tongue' },
                { e: '😜', k: 'winking face with tongue joke' },
                { e: '🤪', k: 'zany face goofy crazy' },
                { e: '😝', k: 'squinting face with tongue' },
                { e: '🤑', k: 'money-mouth face rich cash' },
                { e: '🤗', k: 'smiling face with open hands hug' },
                { e: '🤭', k: 'face with hand over mouth oops' },
                { e: '🤫', k: 'shushing face quiet silence' },
                { e: '🤔', k: 'thinking face hmm' },
                { e: '🤐', k: 'zipper-mouth face secret' },
                { e: '🤨', k: 'face with raised eyebrow suspicious' },
                { e: '😐', k: 'neutral face straight' },
                { e: '😑', k: 'expressionless face' },
                { e: '😶', k: 'face without mouth' },
                { e: '😏', k: 'smirking face smug' },
                { e: '😒', k: 'unamused face meh' },
                { e: '🙄', k: 'face with rolling eyes eye roll' },
                { e: '😬', k: 'grimacing face awkward' },
                { e: '🤥', k: 'lying face pinocchio' },
                { e: '😌', k: 'relieved face calm' },
                { e: '😔', k: 'pensive face sad' },
                { e: '😪', k: 'sleepy face' },
                { e: '🤤', k: 'drooling face' },
                { e: '😴', k: 'sleeping face zzz' },
                { e: '😷', k: 'face with medical mask sick' },
                { e: '🤒', k: 'face with thermometer fever' },
                { e: '🤕', k: 'face with head-bandage hurt' },
                { e: '🤢', k: 'nauseated face gross' },
                { e: '🤮', k: 'face vomiting puking' },
                { e: '🤧', k: 'sneezing face cold' },
                { e: '🥵', k: 'hot face sweating heat' },
                { e: '🥶', k: 'cold face freezing blue' },
                { e: '🥴', k: 'woozy face dizzy drunk' },
                { e: '😵', k: 'face with crossed-out eyes knockout' },
                { e: '🤯', k: 'exploding head mind blown' },
                { e: '🤠', k: 'cowboy hat face' },
                { e: '🥳', k: 'partying face celebration party' },
                { e: '😎', k: 'smiling face with sunglasses cool' },
                { e: '🤓', k: 'nerd face glasses geek' },
                { e: '🧐', k: 'face with monocle classy' },
                { e: '😕', k: 'confused face' },
                { e: '😟', k: 'worried face' },
                { e: '🙁', k: 'slightly frowning face' },
                { e: '😮', k: 'face with open mouth surprised' },
                { e: '😯', k: 'hushed face' },
                { e: '😲', k: 'astonished face shock' },
                { e: '😳', k: 'flushed face embarrassed' },
                { e: '🥺', k: 'pleading face puppy eyes' },
                { e: '😦', k: 'frowning face with open mouth' },
                { e: '😨', k: 'fearful face scared' },
                { e: '😰', k: 'anxious face with sweat nervous' },
                { e: '😥', k: 'sad but relieved face' },
                { e: '😢', k: 'crying face tear' },
                { e: '😭', k: 'loudly crying face sobbing' },
                { e: '😱', k: 'face screaming in fear scream' },
                { e: '😖', k: 'confounded face frustrated' },
                { e: '😣', k: 'persevering face struggling' },
                { e: '😞', k: 'disappointed face' },
                { e: '😓', k: 'downcast face with sweat' },
                { e: '😩', k: 'weary face tired' },
                { e: '😫', k: 'tired face exhausted' },
                { e: '🥱', k: 'yawning face bored sleep' },
                { e: '😤', k: 'face with steam from nose proud angry' },
                { e: '😡', k: 'enraged face mad' },
                { e: '😠', k: 'angry face' },
                { e: '🤬', k: 'face with symbols on mouth swearing' },
                { e: '😈', k: 'smiling face with horns devil evil' },
                { e: '👿', k: 'angry face with horns demon' },
                { e: '💀', k: 'skull dead dead' },
                { e: '☠️', k: 'skull and crossbones poison danger' },
                { e: '💩', k: 'pile of poo poop' },
                { e: '🤡', k: 'clown face' },
                { e: '👻', k: 'ghost halloween boo' },
                { e: '👽', k: 'alien ufo' },
                { e: '🤖', k: 'robot face bot' },
                { e: '❤️', k: 'red heart love' },
                { e: '🧡', k: 'orange heart' },
                { e: '💛', k: 'yellow heart' },
                { e: '💚', k: 'green heart' },
                { e: '💙', k: 'blue heart' },
                { e: '💜', k: 'purple heart' },
                { e: '🖤', k: 'black heart' },
                { e: '🤍', k: 'white heart' },
                { e: '🤎', k: 'brown heart' },
                { e: '💔', k: 'broken heart heartbreak' },
                { e: '❣️', k: 'heart exclamation' },
                { e: '💕', k: 'two hearts' },
                { e: '💞', k: 'revolving hearts' },
                { e: '💓', k: 'beating heart' },
                { e: '💗', k: 'growing heart' },
                { e: '💖', k: 'sparkling heart' },
                { e: '💘', k: 'heart with arrow cupid' },
                { e: '💝', k: 'heart with ribbon gift' },
                { e: '🔥', k: 'fire flame lit hot' },
                { e: '✨', k: 'sparkles shining magic' },
                { e: '⭐', k: 'star favorite' },
                { e: '🌟', k: 'glowing star' },
                { e: '💫', k: 'dizzy star' },
                { e: '💥', k: 'collision boom bang' },
                { e: '💯', k: 'hundred points 100 perfect' }
            ]
        },
        {
            id: 'people',
            name: 'People & Body',
            icon: '👋',
            emojis: [
                { e: '👋', k: 'waving hand hello bye' },
                { e: '🤚', k: 'raised back of hand' },
                { e: '🖐️', k: 'hand with fingers splayed five' },
                { e: '✋', k: 'raised hand stop high five' },
                { e: '🖖', k: 'vulcan salute spock' },
                { e: '👌', k: 'ok hand okay perfect' },
                { e: '🤌', k: 'pinched fingers italian' },
                { e: '🤏', k: 'pinching hand small tiny' },
                { e: '✌️', k: 'victory hand peace two' },
                { e: '🤞', k: 'crossed fingers luck' },
                { e: '🤟', k: 'love-you gesture ily' },
                { e: '🤘', k: 'sign of the horns rock on' },
                { e: '🤙', k: 'call me hand shaka' },
                { e: '👈', k: 'backhand index pointing left' },
                { e: '👉', k: 'backhand index pointing right' },
                { e: '👆', k: 'backhand index pointing up' },
                { e: '🖕', k: 'middle finger' },
                { e: '👇', k: 'backhand index pointing down' },
                { e: '☝️', k: 'index pointing up one' },
                { e: '👍', k: 'thumbs up like approve yes' },
                { e: '👎', k: 'thumbs down dislike no' },
                { e: '✊', k: 'raised fist power' },
                { e: '👊', k: 'oncoming fist brofist punch' },
                { e: '🤛', k: 'left-facing fist' },
                { e: '🤜', k: 'right-facing fist' },
                { e: '👏', k: 'clapping hands applause bravo' },
                { e: '🙌', k: 'raising hands celebrate praise' },
                { e: '👐', k: 'open hands' },
                { e: '🤲', k: 'palms up together prayer' },
                { e: '🤝', k: 'handshake deal agreement' },
                { e: '🙏', k: 'folded hands pray please thank you' },
                { e: '✍️', k: 'writing hand note' },
                { e: '💅', k: 'nail polish sass' },
                { e: '🤳', k: 'selfie phone photo' },
                { e: '💪', k: 'flexed biceps muscle strong flex' },
                { e: '🦾', k: 'mechanical arm cyborg' },
                { e: '🦿', k: 'mechanical leg' },
                { e: '🦵', k: 'leg kick' },
                { e: '🦶', k: 'foot walk' },
                { e: '👂', k: 'ear listen hear' },
                { e: '🦻', k: 'ear with hearing aid' },
                { e: '👃', k: 'nose smell' },
                { e: '🧠', k: 'brain smart think' },
                { e: '👀', k: 'eyes look see gaze' },
                { e: '👁️', k: 'eye view' },
                { e: '👅', k: 'tongue taste lick' },
                { e: '👄', k: 'mouth lips kiss' }
            ]
        },
        {
            id: 'animals',
            name: 'Animals & Nature',
            icon: '🐶',
            emojis: [
                { e: '🐶', k: 'dog face puppy pet' },
                { e: '🐱', k: 'cat face kitten pet' },
                { e: '🐭', k: 'mouse face' },
                { e: '🐹', k: 'hamster face pet' },
                { e: '🐰', k: 'rabbit face bunny easter' },
                { e: '🦊', k: 'fox face sly' },
                { e: '🐻', k: 'bear face' },
                { e: '🐼', k: 'panda face' },
                { e: '🐨', k: 'koala' },
                { e: '🐯', k: 'tiger face wild' },
                { e: '🦁', k: 'lion face king' },
                { e: '🐮', k: 'cow face farm milk' },
                { e: '🐷', k: 'pig face farm pork' },
                { e: '🐸', k: 'frog face ribbit toad' },
                { e: '🐵', k: 'monkey face' },
                { e: '🐔', k: 'chicken farm bird' },
                { e: '🐧', k: 'penguin arctic bird' },
                { e: '🐦', k: 'bird tweet flying' },
                { e: '🦆', k: 'duck quack' },
                { e: '🦅', k: 'eagle freedom' },
                { e: '🦉', k: 'owl wise night' },
                { e: '🦇', k: 'bat night vampire' },
                { e: '🐺', k: 'wolf howl' },
                { e: '🐗', k: 'boar wild pig' },
                { e: '🐴', k: 'horse face pony' },
                { e: '🦄', k: 'unicorn magic fantasy' },
                { e: '🐝', k: 'honeybee bee honey buzz' },
                { e: '🐛', k: 'bug insect caterpillar' },
                { e: '🦋', k: 'butterfly beautiful' },
                { e: '🐌', k: 'snail slow' },
                { e: '🐞', k: 'lady beetle ladybug' },
                { e: '🐜', k: 'ant insect work' },
                { e: '🦟', k: 'mosquito bug bite' },
                { e: '🦗', k: 'cricket chirp' },
                { e: '🕷️', k: 'spider web arachnid' },
                { e: '🦂', k: 'scorpion sting' },
                { e: '🐢', k: 'turtle tortoise slow' },
                { e: '🐍', k: 'snake serpent reptile' },
                { e: '🦎', k: 'lizard reptile gecko' },
                { e: '🐙', k: 'octopus sea ocean tentacle' },
                { e: '🦑', k: 'squid calamari' },
                { e: '🦐', k: 'shrimp prawn seafood' },
                { e: '🦞', k: 'lobster seafood' },
                { e: '🦀', k: 'crab beach seafood' },
                { e: '🐡', k: 'blowfish fish puffer' },
                { e: '🐠', k: 'tropical fish aquarium' },
                { e: '🐟', k: 'fish seafood swimming' },
                { e: '🐬', k: 'dolphin sea ocean flipper' },
                { e: '🐳', k: 'spouting whale ocean' },
                { e: '🐋', k: 'whale ocean big' },
                { e: '🦈', k: 'shark jaws danger' },
                { e: '🐊', k: 'crocodile alligator reptile' },
                { e: '🐅', k: 'tiger jungle stripes' },
                { e: '🐆', k: 'leopard cheetah fast' },
                { e: '🦓', k: 'zebra savannah stripes' },
                { e: '🦍', k: 'gorilla ape' },
                { e: '🦧', k: 'orangutan monkey' },
                { e: '🐘', k: 'elephant trunk africa' },
                { e: '🦛', k: 'hippopotamus hippo' },
                { e: '🦏', k: 'rhinoceros rhino horn' },
                { e: '🐪', k: 'camel desert hump' },
                { e: '🐫', k: 'two-hump camel desert' },
                { e: '🦒', k: 'giraffe tall neck' },
                { e: '🦘', k: 'kangaroo australia jump' },
                { e: '🐃', k: 'water buffalo ox' },
                { e: '🐂', k: 'ox bull horned' },
                { e: '🐄', k: 'cow milk farm dairy' },
                { e: '🐎', k: 'racehorse horse run fast' },
                { e: '🐖', k: 'pig sow swine' },
                { e: '🐏', k: 'ram sheep horns' },
                { e: '🐑', k: 'ewe sheep wool' },
                { e: '🦙', k: 'llama alpaca wool' },
                { e: '🐐', k: 'goat goat farm' },
                { e: '🦌', k: 'deer buck antlers' },
                { e: '🐕', k: 'dog pet loyal' },
                { e: '🐩', k: 'poodle dog fancy' },
                { e: '🦮', k: 'guide dog blind assistance' },
                { e: '🐈', k: 'cat feline meow' },
                { e: '🐓', k: 'rooster cock crow morning' },
                { e: '🦃', k: 'turkey thanksgiving gobble' },
                { e: '🦚', k: 'peacock feathers colorful' },
                { e: '🦜', k: 'parrot pirate talking' },
                { e: '🦢', k: 'swan graceful lake' },
                { e: '🦩', k: 'flamingo pink tropical' },
                { e: '🕊️', k: 'dove peace olive' },
                { e: '🐇', k: 'rabbit bunny hops' },
                { e: '🦝', k: 'raccoon bandit trash' },
                { e: '🦨', k: 'skunk smelly stink' },
                { e: '🦡', k: 'badger fearless' },
                { e: '🦦', k: 'otter river playful' },
                { e: '🦥', k: 'sloth lazy slow' },
                { e: '🐁', k: 'mouse rodent' },
                { e: '🐀', k: 'rat rodent sewer' },
                { e: '🐿️', k: 'chipmunk squirrel nuts' },
                { e: '🦔', k: 'hedgehog sonic spikes' },
                { e: '🐉', k: 'dragon mythical fantasy' },
                { e: '🐲', k: 'dragon face oriental' },
                { e: '🌵', k: 'cactus desert plant' },
                { e: '🎄', k: 'christmas tree holiday x-mas' },
                { e: '🌲', k: 'evergreen tree pine forest' },
                { e: '🌳', k: 'deciduous tree nature park' },
                { e: '🌴', k: 'palm tree beach tropical island' },
                { e: '🌱', k: 'seedling sprout plant grow' },
                { e: '🌿', k: 'herb plant greenery' },
                { e: '☘️', k: 'shamrock saint patrick irish' },
                { e: '🍀', k: 'four leaf clover lucky fortune' },
                { e: '🎍', k: 'pine decoration bamboo' },
                { e: '🎋', k: 'tanabata tree wishing' },
                { e: '🍃', k: 'leaf fluttering in wind breeze' },
                { e: '🍂', k: 'fallen leaf autumn fall' },
                { e: '🍁', k: 'maple leaf canada autumn' },
                { e: '🍄', k: 'mushroom fungus toadstool mario' },
                { e: '🐚', k: 'spiral shell beach ocean sea' },
                { e: '🌾', k: 'sheaf of rice crop grain' },
                { e: '💐', k: 'bouquet flowers romantic' },
                { e: '🌷', k: 'tulip flower spring' },
                { e: '🌹', k: 'rose flower romance red' },
                { e: '🥀', k: 'wilted flower dying sad' },
                { e: '🌺', k: 'hibiscus flower tropical hawaii' },
                { e: '🌸', k: 'cherry blossom sakura pink' },
                { e: '🌼', k: 'blossom flower yellow' },
                { e: '🌻', k: 'sunflower yellow summer sunshine' },
                { e: '🌞', k: 'sun with face sunshine day' },
                { e: '🌝', k: 'full moon face night smile' },
                { e: '🌛', k: 'first quarter moon face night' },
                { e: '🌜', k: 'last quarter moon face night' },
                { e: '🌚', k: 'new moon face dark mysterious' },
                { e: '🌕', k: 'full moon night werewolf' },
                { e: '🌖', k: 'waning gibbous moon space' },
                { e: '🌗', k: 'last quarter moon space' },
                { e: '🌘', k: 'waning crescent moon space' },
                { e: '🌑', k: 'new moon eclipse dark' },
                { e: '🌒', k: 'waxing crescent moon space' },
                { e: '🌓', k: 'first quarter moon space' },
                { e: '🌔', k: 'waxing gibbous moon space' },
                { e: '🌙', k: 'crescent moon night sleep ramadan' },
                { e: '🪐', k: 'ringed planet saturn space' },
                { e: '💫', k: 'dizzy star twinkle' },
                { e: '⭐', k: 'white medium star space rating' },
                { e: '🌟', k: 'glowing star shine sparkle' },
                { e: '☄️', k: 'comet asteroid shooting star' },
                { e: '☀️', k: 'sun sunny weather hot warm' },
                { e: '🌤️', k: 'sun behind small cloud weather' },
                { e: '⛅', k: 'sun behind cloud cloudy overcast' },
                { e: '🌥️', k: 'sun behind large cloud weather' },
                { e: '🌦️', k: 'sun behind rain cloud shower' },
                { e: '☁️', k: 'cloud sky weather' },
                { e: '🌧️', k: 'cloud with rain rainy wet storm' },
                { e: '⛈️', k: 'cloud with lightning and rain thunder' },
                { e: '🌩️', k: 'cloud with lightning bolt flash' },
                { e: '⚡', k: 'high voltage electricity power bolt lightning' },
                { e: '❄️', k: 'snowflake winter snow cold ice' },
                { e: '☃️', k: 'snowman with snow frosty winter' },
                { e: '⛄', k: 'snowman frosty winter cold' },
                { e: '🌬️', k: 'wind face blow cold breeze' },
                { e: '💨', k: 'dashing away fast speed run fart' },
                { e: '🌪️', k: 'tornado cyclone twister storm' },
                { e: '🌫️', k: 'fog misty hazy weather' },
                { e: '🌈', k: 'rainbow pride colorful weather' },
                { e: '☂️', k: 'umbrella rain weather protection' },
                { e: '☔', k: 'umbrella with rain drops wet storm' },
                { e: '💧', k: 'droplet water sweat tear wet' },
                { e: '💦', k: 'sweat droplets splash drip water' },
                { e: '🌊', k: 'water wave tsunami surf ocean' }
            ]
        },
        {
            id: 'food',
            name: 'Food & Drink',
            icon: '🍕',
            emojis: [
                { e: '🍏', k: 'green apple fruit healthy' },
                { e: '🍎', k: 'red apple fruit teacher' },
                { e: '🍐', k: 'pear fruit healthy' },
                { e: '🍊', k: 'tangerine orange citrus fruit' },
                { e: '🍋', k: 'lemon citrus sour yellow' },
                { e: '🍌', k: 'banana fruit monkey potassium' },
                { e: '🍉', k: 'watermelon fruit summer melon' },
                { e: '🍇', k: 'grapes fruit wine purple' },
                { e: '🍓', k: 'strawberry fruit berry sweet' },
                { e: '🫐', k: 'blueberries berry fruit' },
                { e: '🍈', k: 'melon cantaloupe honeydew' },
                { e: '🍒', k: 'cherries fruit sweet red pair' },
                { e: '🍑', k: 'peach fruit sweet butt' },
                { e: '🥭', k: 'mango tropical fruit sweet' },
                { e: '🍍', k: 'pineapple tropical fruit sweet' },
                { e: '🥥', k: 'coconut tropical palm nut' },
                { e: '🥝', k: 'kiwi fruit bird new zealand' },
                { e: '🍅', k: 'tomato vegetable fruit red' },
                { e: '🥑', k: 'avocado guacamole healthy vegan' },
                { e: '🍆', k: 'eggplant aubergine vegetable' },
                { e: '🥔', k: 'potato spud vegetable starch' },
                { e: '🥕', k: 'carrot vegetable orange rabbit' },
                { e: '🌽', k: 'ear of corn maize vegetable' },
                { e: '🌶️', k: 'hot pepper chili spicy' },
                { e: '🫑', k: 'bell pepper paprika vegetable' },
                { e: '🥒', k: 'cucumber pickle vegetable green' },
                { e: '🥬', k: 'leafy green salad lettuce' },
                { e: '🥦', k: 'broccoli vegetable green healthy' },
                { e: '🧄', k: 'garlic cooking vegetable vampire' },
                { e: '🧅', k: 'onion cry vegetable cooking' },
                { e: '🍄', k: 'mushroom toadstool fungus' },
                { e: '🥜', k: 'peanuts nut snack salty' },
                { e: '🌰', k: 'chestnut nut autumn hazel' },
                { e: '🍞', k: 'bread loaf bakery carb toast' },
                { e: '🥐', k: 'croissant bakery pastry french' },
                { e: '🥖', k: 'baguette bread french bakery' },
                { e: '🫓', k: 'flatbread naan pita roti' },
                { e: '🥨', k: 'pretzel twist snack salty' },
                { e: '🥯', k: 'bagel bakery breakfast cream cheese' },
                { e: '🥞', k: 'pancakes breakfast syrup butter' },
                { e: '🧇', k: 'waffle breakfast belgian' },
                { e: '🧀', k: 'cheese wedge swiss dairy yellow' },
                { e: '🍖', k: 'meat on bone manga anime food' },
                { e: '🍗', k: 'poultry leg chicken drumstick' },
                { e: '🥩', k: 'cut of meat steak beef raw' },
                { e: '🥓', k: 'bacon pork breakfast meat' },
                { e: '🍔', k: 'hamburger burger fast food beef' },
                { e: '🍟', k: 'french fries chips fast food' },
                { e: '🍕', k: 'pizza slice italian pepperoni cheese' },
                { e: '🌭', k: 'hot dog frankfurter sausage fast food' },
                { e: '🥪', k: 'sandwich lunch sub bread' },
                { e: '🌮', k: 'taco mexican street food' },
                { e: '🌯', k: 'burrito mexican wrap food' },
                { e: '🫔', k: 'tamale mexican corn food' },
                { e: '🥙', k: 'stuffed flatbread gyro falafel kebab' },
                { e: '🧆', k: 'falafel middle eastern chickpea' },
                { e: '🥚', k: 'egg breakfast chicken protein' },
                { e: '🍳', k: 'cooking egg breakfast sunny side fry' },
                { e: '🥘', k: 'shallow pan of food paella cooking' },
                { e: '🍲', k: 'pot of food stew soup hot' },
                { e: '🫕', k: 'fondue cheese melted swiss pot' },
                { e: '🥣', k: 'bowl with spoon cereal soup oatmeal' },
                { e: '🥗', k: 'green salad healthy diet vegetarian' },
                { e: '🍿', k: 'popcorn movie cinema snack' },
                { e: '🧈', k: 'butter dairy cooking spread' },
                { e: '🧂', k: 'salt shaker sodium seasoning' },
                { e: '🥫', k: 'canned food tin soup can' },
                { e: '🍱', k: 'bento box japanese lunch meal' },
                { e: '🍘', k: 'rice cracker japanese snack' },
                { e: '🍙', k: 'rice ball onigiri japanese' },
                { e: '🍚', k: 'cooked rice bowl staple grain' },
                { e: '🍛', k: 'curry rice indian japanese spicy' },
                { e: '🍜', k: 'steaming bowl ramen noodles soup pho' },
                { e: '🍝', k: 'spaghetti pasta noodles italian dinner' },
                { e: '🍠', k: 'roasted sweet potato snack' },
                { e: '🍢', k: 'oden japanese skewer fishcake' },
                { e: '🍣', k: 'sushi japanese fish roll raw' },
                { e: '🍤', k: 'fried shrimp tempura seafood' },
                { e: '🍥', k: 'fish cake with swirl narutomaki' },
                { e: '🥮', k: 'mooncake mid-autumn festival pastry' },
                { e: '🍡', k: 'dango japanese dessert skewer sweet' },
                { e: '🥟', k: 'dumpling dim sum potsticker gyoza' },
                { e: '🥠', k: 'fortune cookie chinese prophecy' },
                { e: '🥡', k: 'takeout box chinese food container' },
                { e: '🍦', k: 'soft ice cream cone vanilla summer' },
                { e: '🍧', k: 'shaved ice dessert summer' },
                { e: '🍨', k: 'ice cream bowl scoop sundae' },
                { e: '🍩', k: 'doughnut donut sweet pastry glaze' },
                { e: '🍪', k: 'cookie chocolate chip biscuit sweet' },
                { e: '🎂', k: 'birthday cake party celebration' },
                { e: '🍰', k: 'shortcake strawberry cake dessert slice' },
                { e: '🧁', k: 'cupcake sweet bakery muffin frosting' },
                { e: '🥧', k: 'pie apple dessert bakery crust' },
                { e: '🍫', k: 'chocolate bar sweet candy cacao' },
                { e: '🍬', k: 'candy sweet sugar wrapper' },
                { e: '🍭', k: 'lollipop candy sweet spiral sucker' },
                { e: '🍮', k: 'custard pudding flan dessert caramel' },
                { e: '🍯', k: 'honey pot sweet bear bees' },
                { e: '🍼', k: 'baby bottle milk infant drink' },
                { e: '🥛', k: 'glass of milk dairy drink calcium' },
                { e: '☕', k: 'hot beverage coffee tea espresso cafe' },
                { e: '🫖', k: 'teapot tea pot ceramic hot' },
                { e: '🍵', k: 'teacup without handle matcha green tea' },
                { e: '🍶', k: 'sake bottle and cup japanese alcohol' },
                { e: '🍾', k: 'bottle with popping cork champagne celebrate' },
                { e: '🍷', k: 'wine glass red alcohol drink' },
                { e: '🍸', k: 'cocktail glass martini alcohol drink' },
                { e: '🍹', k: 'tropical drink cocktail summer tiki' },
                { e: '🍺', k: 'beer mug alcohol drink pub cheers' },
                { e: '🍻', k: 'clinking beer mugs cheers party toast' },
                { e: '🥂', k: 'clinking glasses celebration champagne toast' },
                { e: '🥃', k: 'tumbler glass whiskey scotch bourbon liquor' },
                { e: '🥤', k: 'cup with straw soda drink soft beverage' },
                { e: '🧋', k: 'bubble tea boba tapioca milk drink' },
                { e: '🧃', k: 'beverage box juice straw box' },
                { e: '🧉', k: 'mate yerba tea drink south america' },
                { e: '🧊', k: 'ice cube cold chill freezer' },
                { e: '🥢', k: 'chopsticks asian utensils eating' },
                { e: '🍽️', k: 'fork and knife with plate dining food' },
                { e: '🍴', k: 'fork and knife cutlery kitchen eating' },
                { e: '🥄', k: 'spoon utensil cutlery soup' },
                { e: '🔪', k: 'kitchen knife chef weapon blade cook' }
            ]
        },
        {
            id: 'activities',
            name: 'Activities & Sports',
            icon: '⚽',
            emojis: [
                { e: '⚽', k: 'soccer ball football sports game' },
                { e: '🏀', k: 'basketball ball sports hoops nba' },
                { e: '🏈', k: 'american football nfl ball sports' },
                { e: '⚾', k: 'baseball ball sports mlb' },
                { e: '🥎', k: 'softball ball sports' },
                { e: '🎾', k: 'tennis racquet ball sports match' },
                { e: '🏐', k: 'volleyball ball sports beach' },
                { e: '🏉', k: 'rugby football sports ball' },
                { e: '🥏', k: 'flying disc frisbee ultimate' },
                { e: '🎱', k: 'pool 8 ball billiards game' },
                { e: '🪀', k: 'yo-yo toy play string' },
                { e: '🏓', k: 'ping pong table tennis paddle sports' },
                { e: '🏸', k: 'badminton shuttlecock racket sports' },
                { e: '🏒', k: 'ice hockey stick puck sports winter' },
                { e: '🏑', k: 'field hockey sports ball stick' },
                { e: '🥍', k: 'lacrosse stick ball sports' },
                { e: '🏏', k: 'cricket bat ball wickets sports' },
                { e: '🪃', k: 'boomerang return toy australia' },
                { e: '🥅', k: 'goal net sports soccer hockey' },
                { e: '⛳', k: 'flag in hole golf green sports' },
                { e: '🪁', k: 'kite wind fly outdoor sky' },
                { e: '🏹', k: 'bow and arrow archery target hunter' },
                { e: '🎣', k: 'fishing pole fish catch rod' },
                { e: '🤿', k: 'diving mask snorkel underwater swim' },
                { e: '🥊', k: 'boxing glove sports fight punch' },
                { e: '🥋', k: 'martial arts uniform karate judo belt' },
                { e: '🎽', k: 'running shirt sash marathon sports' },
                { e: '🛹', k: 'skateboard skate board trick' },
                { e: '🛼', k: 'roller skate skates wheels' },
                { e: '🛷', k: 'sled snow winter sledding' },
                { e: '⛸️', k: 'ice skate skating ice winter' },
                { e: '🥌', k: 'curling stone winter sports ice' },
                { e: '🎿', k: 'skis ski snow winter mountain' },
                { e: '⛷️', k: 'skier skiing snow winter mountain' },
                { e: '🏂', k: 'snowboarder snowboard snow winter' },
                { e: '🪂', k: 'parachute skydive jump extreme' },
                { e: '🏋️', k: 'person lifting weights gym workout fitness' },
                { e: '🤼', k: 'people wrestling sports fight' },
                { e: '🤸', k: 'person cartwheeling gymnastics acrobatic' },
                { e: '⛹️', k: 'person bouncing ball basketball athlete' },
                { e: '🤺', k: 'person fencing sword sports duel' },
                { e: '🏇', k: 'horse racing jockey equestrian sports' },
                { e: '🧘', k: 'person in lotus position yoga meditate zen' },
                { e: '🏄', k: 'person surfing surf water beach ocean' },
                { e: '🏊', k: 'person swimming pool water athlete' },
                { e: '🤽', k: 'person playing water polo sports pool' },
                { e: '🚣', k: 'person rowing boat lake crew kayak' },
                { e: '🧗', k: 'person climbing rock climb mountain' },
                { e: '🚵', k: 'person mountain biking bicycle bike cycle' },
                { e: '🚴', k: 'person biking bicycle bike cycle race' },
                { e: '🏆', k: 'trophy champion win winner cup award' },
                { e: '🥇', k: '1st place medal gold winner champion' },
                { e: '🥈', k: '2nd place medal silver second' },
                { e: '🥉', k: '3rd place medal bronze third' },
                { e: '🏅', k: 'sports medal award prize competition' },
                { e: '🎖️', k: 'military medal honor award hero' },
                { e: '🏵️', k: 'rosette ribbon award decoration' },
                { e: '🎗️', k: 'reminder ribbon awareness support' },
                { e: '🎫', k: 'ticket admission cinema event concert' },
                { e: '🎟️', k: 'admission tickets movie cinema show' },
                { e: '🎪', k: 'circus tent carnival fair big top' },
                { e: '🤹', k: 'person juggling circus perform skills' },
                { e: '🎭', k: 'performing arts theater drama masks act' },
                { e: '🎨', k: 'artist palette art painting colors drawing' },
                { e: '🎬', k: 'clapper board movie film cinema director' },
                { e: '🎤', k: 'microphone mic singing karaoke audio music' },
                { e: '🎧', k: 'headphone music audio listening sound' },
                { e: '🎼', k: 'musical score music notes staff song' },
                { e: '🎹', k: 'musical keyboard piano keys music synth' },
                { e: '🥁', k: 'drum drumsticks rhythm percussion beat' },
                { e: '🪘', k: 'long drum conga djembe bongo' },
                { e: '🎷', k: 'saxophone jazz music instrument brass' },
                { e: '🎺', k: 'trumpet brass music instrument jazz' },
                { e: '🎸', k: 'guitar acoustic rock music instrument' },
                { e: '🪕', k: 'banjo country folk music instrument' },
                { e: '🎻', k: 'violin classical music orchestra strings' },
                { e: '🎲', k: 'game die dice gamble chance board' },
                { e: '♟️', k: 'chess pawn game strategy board' },
                { e: '🎯', k: 'bullseye target dart hit direct' },
                { e: '🎳', k: 'bowling strike ball pins game' },
                { e: '🎮', k: 'video game controller joystick play gaming' },
                { e: '👾', k: 'alien monster retro 8bit arcade space invaders' },
                { e: '🎰', k: 'slot machine casino gamble 777 jackpot' }
            ]
        },
        {
            id: 'travel',
            name: 'Travel & Places',
            icon: '✈️',
            emojis: [
                { e: '🚗', k: 'automobile car travel transport drive' },
                { e: '🚕', k: 'taxi cab uber passenger yellow' },
                { e: '🚙', k: 'sport utility vehicle suv blue travel' },
                { e: '🚌', k: 'bus public transport transit commute' },
                { e: '🚎', k: 'trolleybus electric transit' },
                { e: '🏎️', k: 'racing car race f1 formula fast' },
                { e: '🚓', k: 'police car cop law emergency sirens' },
                { e: '🚑', k: 'ambulance emergency hospital medical 911' },
                { e: '🚒', k: 'fire engine truck emergency 911 firefighter' },
                { e: '🚐', k: 'minibus van camper travel' },
                { e: '🛻', k: 'pickup truck transport vehicle' },
                { e: '🚚', k: 'delivery truck cargo logistics' },
                { e: '🚛', k: 'articulated lorry truck semi highway' },
                { e: '🚜', k: 'tractor farm agriculture' },
                { e: '🦯', k: 'white cane blind mobility accessibility' },
                { e: '🦽', k: 'manual wheelchair disability access' },
                { e: '🦼', k: 'motorized wheelchair disability electric' },
                { e: '🛴', k: 'kick scooter transport city' },
                { e: '🚲', k: 'bicycle bike cycle pedal commute' },
                { e: '🛵', k: 'motor scooter moped vespa delivery' },
                { e: '🏍️', k: 'motorcycle motorbike fast ride speed' },
                { e: '🛺', k: 'auto rickshaw tuk tuk taxi transport' },
                { e: '🚨', k: 'police car light flashing beacon emergency' },
                { e: '🚔', k: 'oncoming police car law cop' },
                { e: '🚍', k: 'oncoming bus transit public' },
                { e: '🚘', k: 'oncoming automobile car front' },
                { e: '🚖', k: 'oncoming taxi cab yellow front' },
                { e: '🚡', k: 'aerial tramway cable car ski mountain' },
                { e: '🚠', k: 'mountain cableway gondola ski' },
                { e: '🚟', k: 'suspension railway train monorail' },
                { e: '🚃', k: 'railway car train carriage' },
                { e: '🚋', k: 'tram car trolley streetcar' },
                { e: '🚞', k: 'mountain railway train travel incline' },
                { e: '🚝', k: 'monorail fast train transport' },
                { e: '🚄', k: 'high-speed train bullet shinkansen fast' },
                { e: '🚅', k: 'bullet train shinkansen fast japan' },
                { e: '🚈', k: 'light rail train transit' },
                { e: '🚂', k: 'locomotive steam train vintage engine' },
                { e: '🚆', k: 'train railway commute transit' },
                { e: '🚇', k: 'metro subway underground tube' },
                { e: '🚊', k: 'tram transit streetcar' },
                { e: '🚉', k: 'station train platform transit' },
                { e: '✈️', k: 'airplane flight travel fly vacation' },
                { e: '🛫', k: 'airplane departure takeoff airport fly' },
                { e: '🛬', k: 'airplane arrival landing airport fly' },
                { e: '🛩️', k: 'small airplane private prop charter' },
                { e: '💺', k: 'seat airplane chair train bus' },
                { e: '🛰️', k: 'satellite orbit space communication' },
                { e: '🚀', k: 'rocket ship space launch blast moon' },
                { e: '🛸', k: 'flying saucer ufo alien space' },
                { e: '🚁', k: 'helicopter chopper fly rotor air' },
                { e: '🛶', k: 'canoe paddle boat kayak river' },
                { e: '⛵', k: 'sailboat boat sailing yacht sea' },
                { e: '🚤', k: 'speedboat motorboat water fast lake' },
                { e: '🛥️', k: 'motor boat yacht luxury sea' },
                { e: '🛳️', k: 'passenger ship cruise luxury ocean vacation' },
                { e: '⛴️', k: 'ferry boat water passenger transit' },
                { e: '🚢', k: 'ship boat cargo titanic transport' },
                { e: '⚓', k: 'anchor marine navy boat nautical' },
                { e: '🪝', k: 'hook pirate fish tool' },
                { e: '⛽', k: 'fuel pump gas station petrol refill' },
                { e: '🚧', k: 'construction barrier warning work detour' },
                { e: '🚦', k: 'vertical traffic light signal stop go' },
                { e: '🚥', k: 'horizontal traffic light signal stop' },
                { e: '🗺️', k: 'world map geography navigation travel' },
                { e: '🗿', k: 'moai easter island statue ancient' },
                { e: '🗽', k: 'statue of liberty new york usa monument' },
                { e: '🗼', k: 'tokyo tower japan landmark monument' },
                { e: '🏰', k: 'castle palace medieval royalty fairy' },
                { e: '🏯', k: 'japanese castle fortress pagoda' },
                { e: '🏟️', k: 'stadium arena sports concert crowd' },
                { e: '🎡', k: 'ferris wheel amusement park carnival ride' },
                { e: '🎢', k: 'roller coaster amusement park thrill ride' },
                { e: '🎠', k: 'carousel horse merry-go-round carnival' },
                { e: '⛲', k: 'fountain water park architecture' },
                { e: '⛱️', k: 'umbrella on ground beach sun shade' },
                { e: '🏖️', k: 'beach with umbrella ocean sea sand vacation' },
                { e: '🏝️', k: 'desert island tropical beach ocean' },
                { e: '🏜️', k: 'desert sahara dry sand cactus' },
                { e: '🌋', k: 'volcano lava eruption mountain rock' },
                { e: '⛰️', k: 'mountain nature hike landscape high' },
                { e: '🏔️', k: 'snow-capped mountain alps summit peak' },
                { e: '🗻', k: 'mount fuji volcano japan landmark snow' },
                { e: '🏕️', k: 'camping tent outdoors nature forest camp' },
                { e: '⛺', k: 'tent camping outdoor scout shelter' },
                { e: '🏠', k: 'house home building residence' },
                { e: '🏡', k: 'house with garden home yard suburb' },
                { e: '🏘️', k: 'houses neighborhood suburb residential' },
                { e: '🏚️', k: 'derelict house abandoned ruined haunted' },
                { e: '🏗️', k: 'building construction crane architecture' },
                { e: '🏭', k: 'factory industry pollution production' },
                { e: '🏢', k: 'office building corporate skyscraper work' },
                { e: '🏬', k: 'department store mall retail shop' },
                { e: '🏣', k: 'japanese post office mail service' },
                { e: '🏤', k: 'post office european mail letter' },
                { e: '🏥', k: 'hospital clinic medical doctor emergency' },
                { e: '🏦', k: 'bank building money finance cash' },
                { e: '🏨', k: 'hotel building room vacation lodging' },
                { e: '🏪', k: 'convenience store 711 mart grocery' },
                { e: '🏫', k: 'school building education student study' },
                { e: '🏩', k: 'love hotel romance heart motel' },
                { e: '💒', k: 'wedding chapel church romance marry' },
                { e: '🏛️', k: 'classical building museum government monument' },
                { e: '⛪', k: 'church religion christian cathedral cross' },
                { e: '🕌', k: 'mosque islam muslim minaret religion' },
                { e: '🛕', k: 'hindu temple temple religion mandir' },
                { e: '🕍', k: 'synagogue jewish religion temple' },
                { e: '⛩️', k: 'shinto shrine torii gate japan temple' },
                { e: '🕋', k: 'kaaba mecca islam pilgrimage hajj' }
            ]
        },
        {
            id: 'objects',
            name: 'Objects',
            icon: '💡',
            emojis: [
                { e: '💡', k: 'light bulb idea bright thinking' },
                { e: '🔦', k: 'flashlight torch electric battery dark' },
                { e: '🏮', k: 'red paper lantern festival celebration' },
                { e: '🪔', k: 'diya lamp oil diwali hindu festival' },
                { e: '🧱', k: 'brick wall build construction material' },
                { e: '🪵', k: 'wood log timber lumber campfire' },
                { e: '🚪', k: 'door entrance exit open house' },
                { e: '🪑', k: 'chair seat sit furniture stool' },
                { e: '🛋️', k: 'couch and lamp sofa furniture living room' },
                { e: '🛏️', k: 'bed sleep hotel furniture bedroom' },
                { e: '🛌', k: 'person in bed sleep hotel resting' },
                { e: '🧸', k: 'teddy bear toy stuffed cute plush' },
                { e: '🖼️', k: 'framed picture art painting gallery photo' },
                { e: '🪞', k: 'mirror reflection glass vanity vanity' },
                { e: '🪟', k: 'window view glass house frame' },
                { e: '🛍️', k: 'shopping bags mall retail purchase buy' },
                { e: '🛒', k: 'shopping cart supermarket retail buy store' },
                { e: '🎁', k: 'wrapped gift present birthday surprise box' },
                { e: '🎈', k: 'balloon party celebration birthday fly' },
                { e: '🎏', k: 'carp streamer fish windsocks festival' },
                { e: '🎀', k: 'ribbon bow decoration gift cute' },
                { e: '🪄', k: 'magic wand wizard fantasy spell cast' },
                { e: '🪅', k: 'piñata party candy mexican celebration' },
                { e: '🎊', k: 'confetti ball celebration party congratulations' },
                { e: '🎉', k: 'party popper celebrate celebration tadas party' },
                { e: '🎎', k: 'japanese dolls hinamatsuri festival' },
                { e: '🏮', k: 'red paper lantern festival light' },
                { e: '✉️', k: 'envelope mail letter message email' },
                { e: '📩', k: 'envelope with arrow incoming mail receive' },
                { e: '📨', k: 'incoming envelope receive mail letter' },
                { e: '📧', k: 'e-mail electronic message inbox' },
                { e: '💌', k: 'love letter romance valentine envelope' },
                { e: '📮', k: 'postbox mailbox letter mail delivery' },
                { e: '📫', k: 'closed mailbox with raised flag mail' },
                { e: '📪', k: 'closed mailbox with lowered flag' },
                { e: '📬', k: 'open mailbox with raised flag mail' },
                { e: '📭', k: 'open mailbox with lowered flag' },
                { e: '📦', k: 'package parcel delivery amazon box cardboard' },
                { e: '🏷️', k: 'label tag price sale brand' },
                { e: '🪧', k: 'placard protest sign rally demonstration' },
                { e: '📁', k: 'file folder organize directory computer' },
                { e: '📂', k: 'open file folder directory documents' },
                { e: '🗂️', k: 'card index dividers organized tabs office' },
                { e: '📅', k: 'calendar date schedule appointment' },
                { e: '📆', k: 'tear-off calendar date time today' },
                { e: '🗒️', k: 'spiral notepad memo notes pad' },
                { e: '🗓️', k: 'spiral calendar date event planner' },
                { e: '📇', k: 'card index rolodex contacts address' },
                { e: '📈', k: 'chart increasing growth up profit stocks' },
                { e: '📉', k: 'chart decreasing loss down slump stocks' },
                { e: '📊', k: 'bar chart analytics presentation statistics' },
                { e: '📋', k: 'clipboard task list checklist audit' },
                { e: '📌', k: 'pushpin thumbtack mark location note' },
                { e: '📍', k: 'round pushpin map pin location spot' },
                { e: '📎', k: 'paperclip attach attachment document paper' },
                { e: '🖇️', k: 'linked paperclips office connect document' },
                { e: '📏', k: 'straight ruler measurement math school' },
                { e: '📐', k: 'triangular ruler geometry architecture math' },
                { e: '✂️', k: 'scissors cut tool barber craft' },
                { e: '🗃️', k: 'card file box archive office storage' },
                { e: '🗄️', k: 'file cabinet office storage archive' },
                { e: '🗑️', k: 'wastebasket trash garbage recycle bin' },
                { e: '🔒', k: 'locked security padlock safe secure' },
                { e: '🔓', k: 'unlocked padlock open access safety' },
                { e: '🔏', k: 'locked with pen privacy security write' },
                { e: '🔐', k: 'locked with key secure password' },
                { e: '🔑', k: 'key access password unlock security' },
                { e: '🗝️', k: 'old key vintage antique secret' },
                { e: '🔨', k: 'hammer tool build repair construction' },
                { e: '🪓', k: 'axe chop wood lumber weapon' },
                { e: '⛏️', k: 'pick mining tool rock dig' },
                { e: '⚒️', k: 'hammer and pick mining tools work' },
                { e: '🛠️', k: 'hammer and wrench tools fix repair settings' },
                { e: '🗡️', k: 'dagger knife weapon sword sharp' },
                { e: '⚔️', k: 'crossed swords fight battle weapon duel' },
                { e: '🔫', k: 'water pistol squirt gun weapon toy' },
                { e: '🪃', k: 'boomerang weapon tool flight return' },
                { e: '🛡️', k: 'shield defense protect armor safety' },
                { e: '🪚', k: 'carpentry saw wood tool cut' },
                { e: '🔧', k: 'wrench spanner tool fix mechanic' },
                { e: '🪛', k: 'screwdriver tool fix assemble screw' },
                { e: '🔩', k: 'nut and bolt metal hardware parts' },
                { e: '⚙️', k: 'gear settings cog options machine' },
                { e: '🗜️', k: 'clamp tool vice squeeze compression' },
                { e: '⚖️', k: 'balance scale justice law court zodiac' },
                { e: '🦯', k: 'white cane blind mobility stick' },
                { e: '🔗', k: 'link chain url hyperlink connect' },
                { e: '⛓️', k: 'chains metal bind locked captive' },
                { e: '🪝', k: 'hook catch tool fish pirate' },
                { e: '🧰', k: 'toolbox tool chest repair kit maintenance' },
                { e: '🧲', k: 'magnet attraction horseshoe science magnetic' },
                { e: '🪜', k: 'ladder climb steps reach high' },
                { e: '⚗️', k: 'alembic chemistry science chemistry flask' },
                { e: '🧪', k: 'test tube chemistry lab science experiment' },
                { e: '🧫', k: 'petri dish biology bacteria lab science' },
                { e: '🧬', k: 'dna genetics biology life science gene' },
                { e: '🔬', k: 'microscope science laboratory biology zoom' },
                { e: '🔭', k: 'telescope astronomy space stars explore' },
                { e: '📡', k: 'satellite antenna communication dish signal' },
                { e: '💉', k: 'syringe vaccine medical injection needle' },
                { e: '🩸', k: 'drop of blood donation medical bleed' },
                { e: '💊', k: 'pill capsule medicine pharmacy drug' },
                { e: '🩹', k: 'adhesive bandage bandaid first aid injury' },
                { e: '🩺', k: 'stethoscope doctor medical health clinic' },
                { e: '🌡️', k: 'thermometer temperature fever warm weather' },
                { e: '📱', k: 'mobile phone cell smartphone iphone screen' },
                { e: '📲', k: 'mobile phone with arrow incoming call' },
                { e: '☎️', k: 'telephone telephone call landline vintage' },
                { e: '📞', k: 'telephone receiver call handset phone' },
                { e: '📟', k: 'pager beeper 90s vintage wireless' },
                { e: '📠', k: 'fax machine office document copy' },
                { e: '🔋', k: 'battery power energy charge electric' },
                { e: '🪫', k: 'low battery dying red power dead' },
                { e: '🔌', k: 'electric plug power outlet cord socket' },
                { e: '💻', k: 'laptop computer pc tech screen macbook' },
                { e: '🖥️', k: 'desktop computer pc monitor workstation' },
                { e: '🖨️', k: 'printer office paper print printout' },
                { e: '⌨️', k: 'keyboard computer typing input type' },
                { e: '🖱️', k: 'computer mouse click cursor scroll' },
                { e: '🖲️', k: 'trackball mouse computer hardware' },
                { e: '💽', k: 'computer disk minidisc optical md' },
                { e: '💾', k: 'floppy disk save 3.5 vintage storage' },
                { e: '💿', k: 'optical disk cd dvd music shiny' },
                { e: '📀', k: 'dvd optical disk movie disc blu-ray' },
                { e: '🧮', k: 'abacus math calculate counting' },
                { e: '🎥', k: 'movie camera film cinema video director' },
                { e: '🎞️', k: 'film frames movie cinema camera roll' },
                { e: '📽️', k: 'film projector movie cinema video vintage' },
                { e: '📺', k: 'television tv show vintage screen broadcast' },
                { e: '📷', k: 'camera photo picture snapshot lens' },
                { e: '📸', k: 'camera with flash photograph photo paparazzi' },
                { e: '📹', k: 'video camera camcorder recording video' },
                { e: '📼', k: 'videocassette vhs tape 80s 90s retro' },
                { e: '🔍', k: 'magnifying glass tilted left search look' },
                { e: '🔎', k: 'magnifying glass tilted right search find' },
                { e: '🕯️', k: 'candle flame wax fire romantic light' },
                { e: '💰', k: 'money bag dollar cash rich wealth' },
                { e: '🪙', k: 'coin currency money cash gold' },
                { e: '💴', k: 'yen banknote currency japan money' },
                { e: '💵', k: 'dollar banknote currency money bill cash' },
                { e: '💶', k: 'euro banknote currency money europe cash' },
                { e: '💷', k: 'pound banknote currency money uk cash' },
                { e: '💸', k: 'money with wings flying away spent cash' },
                { e: '💳', k: 'credit card payment buy visa plastic' }
            ]
        },
        {
            id: 'symbols',
            name: 'Symbols & Flags',
            icon: '🔣',
            emojis: [
                { e: '🏧', k: 'atm sign automated teller cash machine' },
                { e: '🚮', k: 'litter in bin sign trash garbage recycle' },
                { e: '🚰', k: 'potable water drinking tap faucet' },
                { e: '♿', k: 'wheelchair symbol disability handicap accessible' },
                { e: '🚹', k: 'mens room restroom bathroom toilet' },
                { e: '🚺', k: 'womens room restroom bathroom toilet' },
                { e: '🚻', k: 'restroom bathroom toilet wc sign' },
                { e: '🚼', k: 'baby symbol change station nursery infant' },
                { e: '🚾', k: 'water closet bathroom toilet restroom' },
                { e: '🛂', k: 'passport control airport travel border' },
                { e: '🛃', k: 'customs airport border inspect tax' },
                { e: '🛄', k: 'baggage claim luggage airport suitcase' },
                { e: '🛅', k: 'left luggage storage lockers baggage' },
                { e: '⚠️', k: 'warning sign caution alert danger yellow' },
                { e: '🚸', k: 'children crossing road traffic school sign' },
                { e: '⛔', k: 'no entry sign forbidden traffic stop' },
                { e: '🚫', k: 'prohibited sign forbidden ban no stop' },
                { e: '🚳', k: 'no bicycles sign ban no bikes traffic' },
                { e: '🚭', k: 'no smoking sign cigarette tobacco ban' },
                { e: '🚯', k: 'no littering sign trash clean environment' },
                { e: '🚱', k: 'non-potable water sign dont drink tap' },
                { e: '🚷', k: 'no pedestrians sign walking ban traffic' },
                { e: '📵', k: 'no mobile phones sign phone silence quiet' },
                { e: '🔞', k: 'no one under eighteen sign adult mature 18' },
                { e: '☢️', k: 'radioactive symbol nuclear hazard toxic' },
                { e: '☣️', k: 'biohazard symbol biological danger virus' },
                { e: '⬆️', k: 'up arrow direction north pointer' },
                { e: '↗️', k: 'up-right arrow direction diagonal' },
                { e: '➡️', k: 'right arrow direction east next forward' },
                { e: '↘️', k: 'down-right arrow direction diagonal' },
                { e: '⬇️', k: 'down arrow direction south pointer' },
                { e: '↙️', k: 'down-left arrow direction diagonal' },
                { e: '⬅️', k: 'left arrow direction west back' },
                { e: '↖️', k: 'up-left arrow direction diagonal' },
                { e: '↕️', k: 'up-down arrow vertical direction' },
                { e: '↔️', k: 'left-right arrow horizontal direction' },
                { e: '↩️', k: 'right arrow curving left return back' },
                { e: '↪️', k: 'left arrow curving right forward' },
                { e: '⤴️', k: 'right arrow curving up curve' },
                { e: '⤵️', k: 'right arrow curving down curve' },
                { e: '🔃', k: 'clockwise vertical arrows refresh reload' },
                { e: '🔄', k: 'counterclockwise arrows sync repeat spin' },
                { e: '🔙', k: 'back arrow return previous' },
                { e: '🔚', k: 'end arrow finish conclude' },
                { e: '🔛', k: 'on! arrow active start mark' },
                { e: '🔜', k: 'soon arrow coming upcoming future' },
                { e: '🔝', k: 'top arrow highest apex peak' },
                { e: '🛐', k: 'place of worship religion faith pray' },
                { e: '⚛️', k: 'atom symbol science physics nuclear' },
                { e: '🕉️', k: 'om symbol hinduism spiritual yoga' },
                { e: '✡️', k: 'star of david judaism religion jewish' },
                { e: '☸️', k: 'wheel of dharma buddhism religion' },
                { e: '☯️', k: 'yin yang balance taoism philosophy' },
                { e: '✝️', k: 'latin cross christianity religion jesus' },
                { e: '☦️', k: 'orthodox cross christianity religion church' },
                { e: '☪️', k: 'star and crescent islam religion muslim' },
                { e: '☮️', k: 'peace symbol hippie anti-war' },
                { e: '🕎', k: 'menorah hanukkah jewish candelabra' },
                { e: '🔯', k: 'six pointed star hexagram fortune' },
                { e: '♈', k: 'aries zodiac ram astrology horoscope' },
                { e: '♉', k: 'taurus zodiac bull astrology horoscope' },
                { e: '♊', k: 'gemini zodiac twins astrology horoscope' },
                { e: '♋', k: 'cancer zodiac crab astrology horoscope' },
                { e: '♌', k: 'leo zodiac lion astrology horoscope' },
                { e: '♍', k: 'virgo zodiac maiden astrology horoscope' },
                { e: '♎', k: 'libra zodiac scales astrology horoscope' },
                { e: '♏', k: 'scorpio zodiac scorpion astrology horoscope' },
                { e: '♐', k: 'sagittarius zodiac archer astrology' },
                { e: '♑', k: 'capricorn zodiac goat astrology horoscope' },
                { e: '♒', k: 'aquarius zodiac water astrology horoscope' },
                { e: '♓', k: 'pisces zodiac fish astrology horoscope' },
                { e: '⛎', k: 'ophiuchus zodiac serpent astrology' },
                { e: '▶️', k: 'play button media start video' },
                { e: '⏸️', k: 'pause button media wait stop' },
                { e: '⏯️', k: 'play or pause button media toggle' },
                { e: '⏹️', k: 'stop button media halt square' },
                { e: '⏺️', k: 'record button media circle audio' },
                { e: '⏭️', k: 'next track button media skip forward' },
                { e: '⏮️', k: 'last track button media back rewind' },
                { e: '⏩', k: 'fast-forward button media speed' },
                { e: '⏪', k: 'fast reverse button media rewind' },
                { e: '🔀', k: 'shuffle tracks button media random mix' },
                { e: '🔁', k: 'repeat button media loop cycle' },
                { e: '🔂', k: 'repeat single button media loop 1' },
                { e: '🔇', k: 'muted speaker volume sound silent quiet' },
                { e: '🔈', k: 'speaker low volume sound soft' },
                { e: '🔉', k: 'speaker medium volume sound' },
                { e: '🔊', k: 'speaker high volume loud sound noise' },
                { e: '🔔', k: 'bell notification chime alarm alert ring' },
                { e: '🔕', k: 'bell with slash mute silent quiet' },
                { e: '💬', k: 'speech balloon bubble chat text talk' },
                { e: '💭', k: 'thought balloon think bubble dream' },
                { e: '🗯️', k: 'right anger bubble mad scream shout' },
                { e: '♠️', k: 'spade suit poker cards game' },
                { e: '♣️', k: 'club suit poker cards game' },
                { e: '♥️', k: 'heart suit poker cards love game' },
                { e: '♦️', k: 'diamond suit poker cards game' },
                { e: '🃏', k: 'joker wild card playing deck' },
                { e: '🀄', k: 'mahjong red dragon tile game' },
                { e: '🎴', k: 'flower playing cards hanafuda japan' },
                { e: '✔️', k: 'check mark correct pass yes ok tick' },
                { e: '✅', k: 'check mark button green ok approved tick' },
                { e: '❌', k: 'cross mark x cancel wrong no delete' },
                { e: '❎', k: 'cross mark button square cancel' },
                { e: '➕', k: 'plus sign add addition math positive' },
                { e: '➖', k: 'minus sign subtract math negative' },
                { e: '➗', k: 'division sign divide math calculate' },
                { e: '✖️', k: 'multiply sign times math calculate' },
                { e: '♾️', k: 'infinity symbol loop eternal forever' },
                { e: '❓', k: 'red question mark query ask what' },
                { e: '❔', k: 'white question mark query ask' },
                { e: '❕', k: 'white exclamation mark alert caution' },
                { e: '❗', k: 'red exclamation mark alert warning caution' },
                { e: '🏁', k: 'chequered flag race finish racing winner' },
                { e: '🚩', k: 'triangular flag post marker red' },
                { e: '🎌', k: 'crossed flags japan holiday celebration' },
                { e: '🏴', k: 'black flag pirate rebel dark' },
                { e: '🏳️', k: 'white flag surrender peace truce' },
                { e: '🏳️‍🌈', k: 'rainbow flag pride lgbtq gay queer' },
                { e: '🏳️‍⚧️', k: 'transgender flag pride trans identity' },
                { e: '🏴‍☠️', k: 'pirate flag skull crossbones jolly roger' }
            ]
        }
    ];

    class EmojiPicker {
        constructor() {
            this.container = null;
            this.activeMode = 'input'; // 'input' | 'reaction'
            this.currentTarget = null;
            this.onSelectCallback = null;
            this.recentEmojis = this._loadRecent();
            this.activeCatId = 'smileys';

            this._buildDOM();
            this._bindEvents();
        }

        _loadRecent() {
            try {
                const data = localStorage.getItem('lan_recent_emojis');
                return data ? JSON.parse(data) : ['👍', '❤️', '😂', '🔥', '🎉', '🙏', '😍', '👏'];
            } catch (e) {
                return ['👍', '❤️', '😂', '🔥', '🎉', '🙏', '😍', '👏'];
            }
        }

        _saveRecent(emoji) {
            try {
                this.recentEmojis = [emoji, ...this.recentEmojis.filter(x => x !== emoji)].slice(0, 16);
                localStorage.setItem('lan_recent_emojis', JSON.stringify(this.recentEmojis));
            } catch (e) {}
        }

        _buildDOM() {
            this.container = document.createElement('div');
            this.container.className = 'lan-emoji-picker hidden';

            // 1. Search Box
            const searchBox = document.createElement('div');
            searchBox.className = 'lan-emoji-search-box';
            searchBox.innerHTML = `
                <span style="opacity:0.6;font-size:14px;">🔍</span>
                <input type="text" class="lan-emoji-search-input" placeholder="Search emojis…">
            `;
            this.container.appendChild(searchBox);

            // 2. Categories Tab Bar
            const catBar = document.createElement('div');
            catBar.className = 'lan-emoji-categories';
            catBar.innerHTML = `
                <button class="lan-emoji-cat-btn" data-cat="recent" title="Recent">🕒</button>
                ${EMOJI_DATA.map(c => `
                    <button class="lan-emoji-cat-btn ${c.id === 'smileys' ? 'active' : ''}" data-cat="${c.id}" title="${c.name}">${c.icon}</button>
                `).join('')}
            `;
            this.container.appendChild(catBar);

            // 3. Emoji Body
            const body = document.createElement('div');
            body.className = 'lan-emoji-body';
            this.container.appendChild(body);

            document.body.appendChild(this.container);
            this.bodyEl = body;
            this.searchInput = searchBox.querySelector('input');
            this.catBar = catBar;

            this.renderCategory('smileys');
        }

        _bindEvents() {
            // Category navigation
            this.catBar.addEventListener('click', (e) => {
                const btn = e.target.closest('.lan-emoji-cat-btn');
                if (!btn) return;
                const catId = btn.getAttribute('data-cat');
                this.catBar.querySelectorAll('.lan-emoji-cat-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.searchInput.value = '';
                this.renderCategory(catId);
            });

            // Live Search
            this.searchInput.addEventListener('input', (e) => {
                const query = e.target.value.trim().toLowerCase();
                if (!query) {
                    this.renderCategory(this.activeCatId);
                } else {
                    this.renderSearch(query);
                }
            });

            // Emoji Selection
            this.bodyEl.addEventListener('click', (e) => {
                const item = e.target.closest('.lan-emoji-item');
                if (!item) return;
                const emoji = item.textContent.trim();
                this._saveRecent(emoji);

                if (typeof this.onSelectCallback === 'function') {
                    this.onSelectCallback(emoji);
                }
                this.close();
            });

            // Click outside to dismiss
            document.addEventListener('mousedown', (e) => {
                if (!this.container.classList.contains('hidden') &&
                    !this.container.contains(e.target) &&
                    (!this.triggerBtn || !this.triggerBtn.contains(e.target))) {
                    this.close();
                }
            });

            // Escape key
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && !this.container.classList.contains('hidden')) {
                    this.close();
                }
            });
        }

        renderCategory(catId) {
            this.activeCatId = catId;
            this.bodyEl.innerHTML = '';

            if (catId === 'recent') {
                const title = document.createElement('div');
                title.className = 'lan-emoji-section-title';
                title.textContent = 'Recently Used';
                this.bodyEl.appendChild(title);

                const grid = document.createElement('div');
                grid.className = 'lan-emoji-grid';
                grid.innerHTML = this.recentEmojis.map(em => `<div class="lan-emoji-item">${em}</div>`).join('');
                this.bodyEl.appendChild(grid);
                return;
            }

            const cat = EMOJI_DATA.find(c => c.id === catId);
            if (!cat) return;

            const title = document.createElement('div');
            title.className = 'lan-emoji-section-title';
            title.textContent = cat.name;
            this.bodyEl.appendChild(title);

            const grid = document.createElement('div');
            grid.className = 'lan-emoji-grid';
            grid.innerHTML = cat.emojis.map(item => `<div class="lan-emoji-item" title="${item.k}">${item.e}</div>`).join('');
            this.bodyEl.appendChild(grid);
        }

        renderSearch(query) {
            this.bodyEl.innerHTML = '';
            let matches = [];

            for (const cat of EMOJI_DATA) {
                for (const item of cat.emojis) {
                    if (item.k.includes(query) || item.e === query) {
                        matches.push(item);
                        if (matches.length >= 80) break;
                    }
                }
                if (matches.length >= 80) break;
            }

            const title = document.createElement('div');
            title.className = 'lan-emoji-section-title';
            title.textContent = matches.length > 0 ? `Search Results (${matches.length})` : 'No emojis found';
            this.bodyEl.appendChild(title);

            if (matches.length > 0) {
                const grid = document.createElement('div');
                grid.className = 'lan-emoji-grid';
                grid.innerHTML = matches.map(item => `<div class="lan-emoji-item" title="${item.k}">${item.e}</div>`).join('');
                this.bodyEl.appendChild(grid);
            }
        }

        open({ anchor, mode, onSelect, triggerBtn }) {
            this.activeMode = mode || 'input';
            this.currentTarget = anchor;
            this.triggerBtn = triggerBtn || null;
            this.onSelectCallback = onSelect;

            this.searchInput.value = '';
            this.renderCategory(this.activeCatId);
            this.container.classList.remove('hidden');

            // Position next to anchor
            const rect = (triggerBtn || anchor).getBoundingClientRect();
            const pickerWidth = 340;
            const pickerHeight = 380;

            let top = rect.top - pickerHeight - 8;
            let left = rect.left;

            // Flip downward if no space above
            if (top < 10) {
                top = rect.bottom + 8;
            }
            // Keep on screen horizontally
            if (left + pickerWidth > window.innerWidth - 10) {
                left = window.innerWidth - pickerWidth - 10;
            }
            if (left < 10) left = 10;

            this.container.style.top = `${window.scrollY + top}px`;
            this.container.style.left = `${window.scrollX + left}px`;

            this.searchInput.focus();
        }

        close() {
            this.container.classList.add('hidden');
            this.onSelectCallback = null;
        }

        insertAtCursor(textarea, emoji) {
            if (!textarea) return;
            const start = textarea.selectionStart || 0;
            const end = textarea.selectionEnd || 0;
            const text = textarea.value;
            textarea.value = text.substring(0, start) + emoji + text.substring(end);
            textarea.selectionStart = textarea.selectionEnd = start + emoji.length;
            textarea.focus();
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }

    window.LANEmojiPicker = new EmojiPicker();
})(window);
```

- [x] **Step 3: Commit Emoji Engine files**
```bash
git add static/css/emoji-picker.css static/js/emoji-picker.js
git commit -m "feat(emoji): add WhatsApp-style categorized searchable emoji keyboard and picker"
```

---

### Task 3: Global Notification Integration into Base Pages (`index.html`, `uploads.html`, `watch.html`)

**Files:**
- Modify: `templates/index.html`
- Modify: `templates/uploads.html`
- Modify: `templates/watch.html`

- [x] **Step 1: Update `templates/index.html`**
Include `notifications.css` in `<head>` and `notifications.js` before `</body>`. Initialize `LANNotifications.init({ socket, currentUser: userName, activeChannel: 'index' })`.

- [x] **Step 2: Update `templates/uploads.html`**
Include `notifications.css` in `<head>` and `notifications.js` before `</body>`. Initialize `LANNotifications.init({ socket, currentUser, activeChannel: 'uploads' })`.

- [x] **Step 3: Update `templates/watch.html`**
Include `notifications.css` in `<head>` and `notifications.js` before `</body>`. Initialize `LANNotifications.init({ socket, currentUser, activeChannel: 'watch' })`.

- [x] **Step 4: Commit Global Notification Integration**
```bash
git add templates/index.html templates/uploads.html templates/watch.html
git commit -m "feat(notifications): attach global notifications and WhatsApp chime to dashboard, files, and watch party"
```

---

### Task 4: Input Emoji Button, Reactions & Notifications in `templates/chat.html`

**Files:**
- Modify: `templates/chat.html`

- [x] **Step 1: Add Emoji Picker Button to Input Bar**
In `templates/chat.html`, add an emoji button `😊` inside `.input-wrapper` right before the textarea or in `.input-actions`:
```html
<button class="icon-btn" id="emojiToggleBtn" type="button" title="Insert emoji" aria-label="Insert emoji">
    <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="10"/>
        <path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"/>
    </svg>
</button>
```

- [x] **Step 2: Include stylesheets and scripts**
Include `notifications.css` and `emoji-picker.css` in `<head>`.
Include `notifications.js` and `emoji-picker.js` before `</body>`.

- [x] **Step 3: Wire Emoji Button & Message Reactions to `LANEmojiPicker`**
Connect `emojiToggleBtn` click to open `LANEmojiPicker.open({ anchor: messageInput, triggerBtn: emojiToggleBtn, onSelect: (emoji) => LANEmojiPicker.insertAtCursor(messageInput, emoji) })`.
Connect reaction button `+` on messages to open `LANEmojiPicker.open({ anchor: messageEl, mode: 'reaction', onSelect: (emoji) => addReaction(messageId, emoji) })`.

- [x] **Step 4: Wire Notification System in `chat.html`**
Initialize `LANNotifications.init({ socket, currentUser: userName, activeChannel: 'chat' })`.

- [x] **Step 5: Commit `chat.html` changes**
```bash
git add templates/chat.html
git commit -m "feat(chat): integrate WhatsApp input emoji button, reaction picker, and notifications"
```

---

### Task 5: Input Emoji Button, Reactions & Notifications in `templates/dm.html`

**Files:**
- Modify: `templates/dm.html`

- [x] **Step 1: Add Emoji Button to DM Input Bar**
Add the identical `emojiToggleBtn` inside DM message input bar.

- [x] **Step 2: Include stylesheets and scripts**
Include `notifications.css` and `emoji-picker.css` in `<head>`.
Include `notifications.js` and `emoji-picker.js` before `</body>`.

- [x] **Step 3: Wire Emoji Picker to DM input and DM reactions**
Connect `LANEmojiPicker` to `messageInput` and message reactions in `dm.html`.

- [x] **Step 4: Wire Notification System with Active Partner**
Initialize `LANNotifications.init({ socket, currentUser: userName, activeChannel: 'dm', activePartner: partnerUser })`.

- [x] **Step 5: Commit `dm.html` changes**
```bash
git add templates/dm.html
git commit -m "feat(dm): integrate WhatsApp input emoji button, reaction picker, and notifications"
```

---

### Task 6: End-to-End Verification & QA

- [x] **Step 1: Verify syntax and template rendering**
Run `python3 -m py_compile app.py` and inspect DOM integrity.

- [x] **Step 2: Test Emoji Picker Functionality**
- Open `/chat`:
  - Click 😊 button: verify category tabs switch, search filters emojis in real time, clicking an emoji inserts at cursor in `messageInput`.
  - Click reaction on message: verify full emoji picker opens and clicking adds reaction.
- Open `/dm`:
  - Verify same emoji keyboard behaviors.

- [x] **Step 3: Test Notification Suite**
- Background tab: send message from another tab/window. Verify Web Audio two-tone WhatsApp chime plays, desktop push notification triggers, and tab title updates to `(1) LAN Chat`.
- Foreground on `/uploads`: receive chat message. Verify in-app floating banner toast slides down with avatar and preview, clicking navigates to `/chat`.
- Foreground on active chat: verify alerts are suppressed and message renders smoothly.

- [x] **Step 4: Final Git Status & Clean Commit**
```bash
git status
```
