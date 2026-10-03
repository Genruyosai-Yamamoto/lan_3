# Chat Notifications (WhatsApp-like) + Full Emoji Picker Design

## Overview
Integrate WhatsApp-like chat notifications and a full emoji picker into the LAN chat (public + DMs), with dynamic title bar updates showing unread counts. Notifications trigger for both DMs and public chat when the window is not focused, respecting conversation focus (don’t notify for the currently open conversation). System notifications use channel-aware titles with message previews.

## Goals
- Browser system notifications (when app in background/tab not focused) with channel-aware content: `[DM] [Name]` or `[Chat] [Name]` + message preview
- Dynamic document title updates showing number of new messages (e.g., `(3) Team Chat`)
- Hybrid focus tracking: global window focus + currently open conversation (to avoid counting/alerting for active conversation)
- Expand emoji picker from 8 to ~78 common emojis (WhatsApp-like coverage), keep reaction flow working
- Minimal, non-breaking changes to existing Flask/SocketIO backend
- Self-contained in templates + small client state

## Design

### 1) Focus & Unread State (client-side)
Track:
- `windowFocused = true/false` (via `visibilitychange` + `focus`/`blur`)
- `currentPage = 'chat' | 'dm'` (derived from URL or template var)
- `activeDMPartner = username | null` (for DM page; set from template `{{ partner }}`)
- `activeChatOpen = true` for chat page when focused in context; for DM, active if talking to specific partner
- `unreadTotal = { public: n, dm: { [partner]: n, total: n } }` aggregated

Rules (per (d)): when a new message arrives, increment unread for that channel/conversation UNLESS (window focused AND it’s for the currently open conversation). System notifications fire only when window NOT focused AND message is not for currently open conversation (or if no conversation is “active” in view) — for both public+DM per (c).

Dynamic title:
- If any unreadTotal.total > 0 and window not focused (or even when focused, show count while there are unreads not in active view? WhatsApp web shows unread count in title/tab; typically `(n) Chat` when unread exists). Design: show `({totalUnread}) <pageTitle>` whenever `totalUnread > 0`; otherwise show base title.

### 2) Browser System Notifications
Use `Notification.requestPermission()` on first user interaction (click/typing). On new message while not focused and qualifies:
- Title: `[DM] ${sender}` if DM and not active DM with that sender; `[Chat] ${sender}` if public and not in active chat view? Or `[Chat] ${sender}` vs `[DM] ${sender}`. (b): channel-aware includes channel context.
- Body: first ~80 chars of message content (strip HTML, handle deleted/audio). For audio, show `🎤 Voice Message`. For encrypted DM text, we may show preview after decryption if available client-side (as already done in appendMessage). 
- Icon/behavior: use default; click focuses window (optional).

Permission: request once on init after first user gesture (safe).

### 3) Emoji Picker Expansion
Replace COMMON_EMOJIS (8) with expanded set of ~78 common emojis (Unicode) in both `chat.html` and `dm.html`. Keep same popup UI, grid layout (CSS already uses grid). Also consider search? Not requested; keep simple list.

Suggested set (covers reactions + common WhatsApp-like): see values below.

### 4) Template Changes
Chat (`templates/chat.html`), DM (`templates/dm.html`):
- Add focus tracking, unread counters, title updater
- Add Notification permission request + notification sender
- Replace emoji arrays with expanded set
- Hook into `new_message` / `new_private_message` to update unread/title/notify

### 5) Non-breaking
No backend changes required (events already emit full data). State is client-side only.

## Implementation Notes
- Decrypt preview for DM before notifying if sharedKey available (matches existing behavior)
- Ignore messages from self for notification? Usually yes (WhatsApp doesn’t notify you of your own messages). Check sender vs current user.
- Handle audio/file types in preview.
- Title updates on focus change and on new messages/read.

## Approval
Present this design for approval, then write spec to docs/superpowers/specs/2026-10-04-chat-notifications-emoji-design.md and proceed to writing-plans.

## Emoji Set (78)
['😀','😁','😂','🤣','😊','😉','😍','😘','🤔','🤨','😐','😔','😢','😭','😠','🤪','😴','🤢','😞','👍','👎','👏','🙌','🙏','👐','✌️','❤️','🧡','💛','💚','💙','💜','💖','💔','🔥','✨','⭐','💫','💯','🎉','🎊','⚠️','🚫','✅','❌','🚀','💬','💭','👀','👇','👆','🎵','🔔','💻','💡','⚙️','😆','😌','😏','🧐','🌈','🍕','🍔','🍨','🐶','🐱','🦄','🐉','🚗','✈️','🚢','🚆','☀️','🌙','☁️','⚡','❄️','☂️']

## Risks
- Browser Notification API requires HTTPS in some contexts; app already uses HTTPS/SSL in some modes; otherwise falls back to no system notifications (graceful degradation)
- No PWA/service worker added (not requested) — uses standard Notification API
- Title updates are cheap and client-only

## Testing
- Receive public message while in another tab: title updates, system notification appears (if permitted)
- Receive DM for different partner while in chat tab: notification fires, title shows count
- Receive DM for active partner while focused: no notification, unread not incremented for that active convo
- Emoji picker shows 78 emojis, reactions work as before
