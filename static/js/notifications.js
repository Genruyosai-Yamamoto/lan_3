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
            if (document.body) {
                this._createToastContainer();
            } else {
                document.addEventListener('DOMContentLoaded', () => this._createToastContainer());
            }
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
            if (!this.toastContainer || !this.toastContainer.parentNode) {
                const existing = document.querySelector('.lan-toast-container');
                if (existing) {
                    this.toastContainer = existing;
                } else if (document.body) {
                    this.toastContainer = document.createElement('div');
                    this.toastContainer.className = 'lan-toast-container';
                    document.body.appendChild(this.toastContainer);
                }
            }
            return this.toastContainer;
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
            let isCurrentChatActive = this.isWindowFocused && this.activeChannel === 'chat' && type === 'chat';
            let isCurrentDMActive = this.isWindowFocused && this.activeChannel === 'dm' && type === 'dm' &&
                (this.activePartner === sender || this.activePartner === receiver);

            // Active view suppression rule: If user is scrolled up (>150px from bottom), do not suppress!
            if (isCurrentChatActive) {
                const area = document.getElementById('messagesArea');
                if (area && (area.scrollHeight - area.scrollTop - area.clientHeight > 150)) {
                    isCurrentChatActive = false; // Scrolled up in chat -> show toast banner & chime
                }
            }
            if (isCurrentDMActive) {
                const area = document.getElementById('messagesArea');
                if (area && (area.scrollHeight - area.scrollTop - area.clientHeight > 150)) {
                    isCurrentDMActive = false; // Scrolled up in DM -> show toast banner & chime
                }
            }

            if (isCurrentChatActive || isCurrentDMActive) {
                // User is actively reading this conversation at the bottom
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
            const targetUrl = type === 'dm' ? `/dm/start_dm/${encodeURIComponent(sender)}` : `/chat`;

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

            const container = this._createToastContainer();
            if (container) {
                container.appendChild(toast);
            }

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
