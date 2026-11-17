/**
 * LanCallManager - Universal 100% Offline LAN WebRTC Call Manager
 * 
 * Supports:
 * - 1:1 Personal Audio & Video Calls (Direct Messages)
 * - Multi-Peer Mesh Group Video Huddles (Team Chat)
 * - Offline Web Audio API Synthesized Chimes (Ringtone, Join, Leave, Hand Raise)
 * - Real-time Voice Activity Detection (AnalyserNode audio level indicators)
 * - Screen Sharing with live track replacement (replaceTrack)
 * - Camera & Mic toggle with fallback avatar tiles
 * - Hand Raise system with synchronized state
 */

(function (window) {
    'use strict';

    // Pure Offline LAN Configuration: No external STUN/TURN servers required.
    // Host ICE candidates generated locally on the subnet connect directly peer-to-peer.
    const RTC_CONFIG = {
        iceServers: []
    };

    // Hardened audio constraints to eliminate acoustic feedback, self-echo, and howling loops
    const HARDENED_AUDIO_CONSTRAINTS = {
        echoCancellation: { ideal: true },
        noiseSuppression: { ideal: true },
        autoGainControl: { ideal: true },
        channelCount: { ideal: 1 },
        googEchoCancellation: true,
        googAutoGainControl: true,
        googNoiseSuppression: true,
        googHighpassFilter: true,
        googTypingNoiseDetection: true
    };

    /**
     * Offline Sound Synthesizer using Web Audio API
     */
    class OfflineCallAudio {
        constructor(sharedAudioCtx = null) {
            this.sharedAudioCtx = sharedAudioCtx;
            this.ctx = (typeof sharedAudioCtx === 'function') ? null : sharedAudioCtx;
            this.ringInterval = null;
            this.activeOscillators = [];
        }

        initContext() {
            if (typeof this.sharedAudioCtx === 'function') {
                this.ctx = this.sharedAudioCtx();
            } else if (this.sharedAudioCtx) {
                this.ctx = this.sharedAudioCtx;
            } else if (!this.ctx) {
                const AudioCtx = window.AudioContext || window.webkitAudioContext;
                if (AudioCtx) {
                    this.ctx = new AudioCtx();
                }
            }
            if (this.ctx && this.ctx.state === 'suspended') {
                this.ctx.resume().catch(() => {});
            }
            return this.ctx;
        }

        // Dual-tone ringing sound (Standard telephone ring cadence: 440Hz + 480Hz)
        playRingTone() {
            this.stopRingTone();
            const ctx = this.initContext();
            if (!ctx) return;

            const ringBurst = () => {
                if (!this.ringInterval) return;
                try {
                    const osc1 = ctx.createOscillator();
                    const osc2 = ctx.createOscillator();
                    const gain = ctx.createGain();

                    osc1.type = 'sine';
                    osc1.frequency.setValueAtTime(440, ctx.currentTime);
                    osc2.type = 'sine';
                    osc2.frequency.setValueAtTime(480, ctx.currentTime);

                    gain.gain.setValueAtTime(0.08, ctx.currentTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 1.2);

                    osc1.connect(gain);
                    osc2.connect(gain);
                    gain.connect(ctx.destination);

                    osc1.start();
                    osc2.start();
                    osc1.stop(ctx.currentTime + 1.2);
                    osc2.stop(ctx.currentTime + 1.2);
                } catch (e) {
                    console.warn('Audio ringtone error:', e);
                }
            };

            ringBurst();
            this.ringInterval = setInterval(ringBurst, 2800);
        }

        stopRingTone() {
            if (this.ringInterval) {
                clearInterval(this.ringInterval);
                this.ringInterval = null;
            }
        }

        // Pleasant notification chimes
        playChime(type) {
            const ctx = this.initContext();
            if (!ctx) return;

            try {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);

                const now = ctx.currentTime;
                if (type === 'join') {
                    // Ascending cheerful chime
                    osc.frequency.setValueAtTime(523.25, now); // C5
                    osc.frequency.exponentialRampToValueAtTime(659.25, now + 0.15); // E5
                    gain.gain.setValueAtTime(0.12, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
                    osc.start(now);
                    osc.stop(now + 0.35);
                } else if (type === 'leave') {
                    // Descending leave chime
                    osc.frequency.setValueAtTime(587.33, now); // D5
                    osc.frequency.exponentialRampToValueAtTime(440.00, now + 0.18); // A4
                    gain.gain.setValueAtTime(0.12, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
                    osc.start(now);
                    osc.stop(now + 0.35);
                } else if (type === 'hand') {
                    // Double blip for hand raise
                    osc.frequency.setValueAtTime(880, now);
                    gain.gain.setValueAtTime(0.15, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
                    osc.start(now);
                    osc.stop(now + 0.2);
                }
            } catch (e) {
                console.warn('Audio chime error:', e);
            }
        }
    }

    /**
     * Main LanCallManager Class
     */
    class LanCallManager {
        constructor(options = {}) {
            this.socket = options.socket;
            this.currentUser = options.currentUser || 'Anonymous';

            // Callbacks
            this.onRemoteStreamAdded = options.onRemoteStreamAdded || (() => {});
            this.onRemoteStreamRemoved = options.onRemoteStreamRemoved || (() => {});
            this.onSpeakingChange = options.onSpeakingChange || (() => {});
            this.onHandChange = options.onHandChange || (() => {});
            this.onCallEnded = options.onCallEnded || (() => {});
            this.onCallStatusChange = options.onCallStatusChange || (() => {});
            this.onLocalStreamReady = options.onLocalStreamReady || (() => {});
            this.onRemoteVolumeChange = options.onRemoteVolumeChange || (() => {});

            // Shared AudioContext (Unified across LanCallManager and OfflineCallAudio)
            this.sharedAudioCtx = null;
            this.audioCtx = null;

            // Audio effects using unified AudioContext
            this.audioPlayer = new OfflineCallAudio(() => this.getSharedAudioContext());

            // Remote output volume state (default 0.75 / safe level)
            this.remoteVolume = 0.75;

            // Local Media State
            this.localStream = null;
            this.localPreviewStream = null;
            this.cameraTrack = null;
            this.micTrack = null;
            this.screenStream = null;
            this.isScreenSharing = false;
            this.isHandRaised = false;
            this.callType = 'video'; // 'video' | 'audio'
            this.callMode = null; // 'direct' | 'group' | null

            // 1:1 Direct Call State
            this.partnerName = null;
            this.directPeerConnection = null;
            this.isCaller = false;

            // Group Call State
            this.currentRoom = null;
            // Map of peerId -> { pc: RTCPeerConnection, username: string, stream: MediaStream, analyserNode: AnalyserNode }
            this.groupPeers = new Map();

            // Audio Analysis Loop (Voice Activity Detection)
            this.analysers = new Map(); // id -> { source, analyser, dataArray, threshold, callback }
            this.speechDetectionInterval = null;

            this._setupSocketListeners();
            this._setupUnloadHandler();
        }

        // ==========================================
        // Local Media Control & Speech Analysis
        // ==========================================

        getSharedAudioContext() {
            if (!this.sharedAudioCtx) {
                const AudioCtx = window.AudioContext || window.webkitAudioContext;
                if (AudioCtx) {
                    this.sharedAudioCtx = new AudioCtx();
                }
            }
            if (this.sharedAudioCtx && this.sharedAudioCtx.state === 'suspended') {
                this.sharedAudioCtx.resume().catch(() => {});
            }
            this.audioCtx = this.sharedAudioCtx;
            if (this.audioPlayer) {
                this.audioPlayer.ctx = this.sharedAudioCtx;
            }
            return this.sharedAudioCtx;
        }

        setRemoteVolume(level) {
            this.remoteVolume = Math.max(0, Math.min(1, Number(level)));
            if (typeof this.onRemoteVolumeChange === 'function') {
                this.onRemoteVolumeChange(this.remoteVolume);
            }
            return this.remoteVolume;
        }

        cycleRemoteVolume() {
            if (this.remoteVolume > 0.5) {
                return this.setRemoteVolume(0.35);
            } else if (this.remoteVolume > 0.1) {
                return this.setRemoteVolume(0.0);
            } else {
                return this.setRemoteVolume(0.75);
            }
        }

        async startLocalMedia(options = { video: true, audio: true }) {
            this.callType = options.video ? 'video' : 'audio';

            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error('MediaDevices API not available. Ensure you are accessing via HTTPS or localhost.');
            }

            try {
                this.localStream = await navigator.mediaDevices.getUserMedia({
                    audio: options.audio === false ? false : HARDENED_AUDIO_CONSTRAINTS,
                    video: options.video ? {
                        width: { ideal: 1280 },
                        height: { ideal: 720 },
                        facingMode: 'user'
                    } : false
                });
            } catch (err) {
                // If camera failed or was denied, attempt audio-only fallback
                if (options.video) {
                    console.warn('Camera acquisition failed, falling back to audio only:', err);
                    this.localStream = await navigator.mediaDevices.getUserMedia({
                        audio: HARDENED_AUDIO_CONSTRAINTS,
                        video: false
                    });
                    this.callType = 'audio';
                } else {
                    throw err;
                }
            }

            const audioTracks = this.localStream.getAudioTracks();
            if (audioTracks.length > 0) {
                this.micTrack = audioTracks[0];
            }

            const videoTracks = this.localStream.getVideoTracks();
            if (videoTracks.length > 0) {
                this.cameraTrack = videoTracks[0];
            }

            // Create isolated video-only preview stream (strictly zero audio tracks to prevent self-echo)
            this.localPreviewStream = new MediaStream(videoTracks);

            // Set up speech detection for local stream
            this._startAudioAnalysis('local', this.localStream, (isSpeaking) => {
                this.onSpeakingChange('local', isSpeaking);
            });

            this.onLocalStreamReady(this.localStream, this.localPreviewStream, this.callType);
            return this.localStream;
        }

        toggleAudio(forceState = null) {
            if (!this.micTrack) return false;
            const newState = forceState !== null ? forceState : !this.micTrack.enabled;
            this.micTrack.enabled = newState;
            return newState;
        }

        toggleVideo(forceState = null) {
            if (!this.cameraTrack) return false;
            const newState = forceState !== null ? forceState : !this.cameraTrack.enabled;
            this.cameraTrack.enabled = newState;
            return newState;
        }

        async toggleScreenShare() {
            if (this.isScreenSharing) {
                this.stopScreenShare();
                return false;
            }

            if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
                throw new Error('Screen sharing is not supported in this browser.');
            }

            try {
                this.screenStream = await navigator.mediaDevices.getDisplayMedia({
                    video: { cursor: 'always' },
                    audio: false
                });

                const screenVideoTrack = this.screenStream.getVideoTracks()[0];
                this.isScreenSharing = true;

                // Replace track on all active peer connections
                await this._replaceOutgoingVideoTrack(screenVideoTrack);

                // Handle native browser "Stop sharing" button
                screenVideoTrack.onended = () => {
                    this.stopScreenShare();
                };

                return true;
            } catch (err) {
                console.warn('Screen share canceled or denied:', err);
                this.isScreenSharing = false;
                return false;
            }
        }

        async stopScreenShare() {
            if (!this.isScreenSharing) return;
            this.isScreenSharing = false;

            if (this.screenStream) {
                this.screenStream.getTracks().forEach(t => t.stop());
                this.screenStream = null;
            }

            // Revert back to camera track if available
            if (this.cameraTrack) {
                await this._replaceOutgoingVideoTrack(this.cameraTrack);
            }
        }

        async _replaceOutgoingVideoTrack(newTrack) {
            const pcs = [];
            if (this.directPeerConnection) {
                pcs.push(this.directPeerConnection);
            }
            this.groupPeers.forEach(peer => {
                if (peer.pc) pcs.push(peer.pc);
            });

            for (const pc of pcs) {
                const senders = pc.getSenders();
                const videoSender = senders.find(s => s.track && s.track.kind === 'video');
                if (videoSender) {
                    try {
                        await videoSender.replaceTrack(newTrack);
                    } catch (e) {
                        console.error('Error replacing video track:', e);
                    }
                }
            }
        }

        toggleHandRaise() {
            this.isHandRaised = !this.isHandRaised;
            this.audioPlayer.playChime('hand');

            if (this.callMode === 'group' && this.socket && this.socket.connected) {
                this.socket.emit('group_call_hand', {
                    room: this.currentRoom,
                    raised: this.isHandRaised
                });
            }

            this.onHandChange('local', this.isHandRaised);
            return this.isHandRaised;
        }

        // ==========================================
        // Web Audio VAD (Voice Activity Detection)
        // ==========================================

        _startAudioAnalysis(id, stream, callback) {
            if (!stream || stream.getAudioTracks().length === 0) return;

            const ctx = this.getSharedAudioContext();
            if (!ctx) return;

            try {
                const source = ctx.createMediaStreamSource(stream);
                const analyser = ctx.createAnalyser();
                analyser.fftSize = 256;
                analyser.smoothingTimeConstant = 0.4;
                source.connect(analyser);
                // Note: AnalyserNode is explicitly NEVER connected to ctx.destination
                // to avoid routing local microphone or remote audio back to speakers.

                const dataArray = new Uint8Array(analyser.frequencyBinCount);
                this.analysers.set(id, {
                    source,
                    analyser,
                    dataArray,
                    callback,
                    isSpeaking: false,
                    silenceCount: 0
                });

                if (!this.speechDetectionInterval) {
                    this.speechDetectionInterval = setInterval(() => this._pollSpeechLevels(), 120);
                }
            } catch (err) {
                console.warn('Could not initialize speech detection for:', id, err);
            }
        }

        _stopAudioAnalysis(id) {
            const entry = this.analysers.get(id);
            if (entry) {
                try {
                    if (entry.source) entry.source.disconnect();
                } catch (e) {}
                try {
                    if (entry.analyser) entry.analyser.disconnect();
                } catch (e) {}
                this.analysers.delete(id);
            }
            if (this.analysers.size === 0 && this.speechDetectionInterval) {
                clearInterval(this.speechDetectionInterval);
                this.speechDetectionInterval = null;
            }
        }

        _pollSpeechLevels() {
            this.analysers.forEach((entry, id) => {
                entry.analyser.getByteFrequencyData(entry.dataArray);
                let sum = 0;
                for (let i = 0; i < entry.dataArray.length; i++) {
                    sum += entry.dataArray[i];
                }
                const average = sum / entry.dataArray.length;
                const threshold = 18; // Sensible voice threshold for normalized byte frequency data

                if (average > threshold) {
                    entry.silenceCount = 0;
                    if (!entry.isSpeaking) {
                        entry.isSpeaking = true;
                        entry.callback(true);
                    }
                } else {
                    entry.silenceCount++;
                    if (entry.isSpeaking && entry.silenceCount > 2) {
                        entry.isSpeaking = false;
                        entry.callback(false);
                    }
                }
            });
        }

        // ==========================================
        // 1:1 Personal Direct Calling
        // ==========================================

        async startDirectCall(receiver, callType = 'video') {
            this.cleanup();
            this.callMode = 'direct';
            this.partnerName = receiver;
            this.callType = callType;
            this.isCaller = true;

            this.onCallStatusChange('Calling...');
            this.audioPlayer.playRingTone();

            await this.startLocalMedia({ video: callType === 'video', audio: true });
            this.directPeerConnection = this._createDirectPeerConnection();

            this.localStream.getTracks().forEach(track => {
                this.directPeerConnection.addTrack(track, this.localStream);
            });

            const offer = await this.directPeerConnection.createOffer();
            await this.directPeerConnection.setLocalDescription(offer);

            this.socket.emit('call_user', {
                sender: this.currentUser,
                receiver: this.partnerName,
                call_type: this.callType,
                offer: offer
            });
        }

        async answerDirectCall(caller, offer, callType = 'video') {
            this.cleanup();
            this.callMode = 'direct';
            this.partnerName = caller;
            this.callType = callType;
            this.isCaller = false;

            this.audioPlayer.stopRingTone();
            this.onCallStatusChange('Connecting...');

            await this.startLocalMedia({ video: callType === 'video', audio: true });
            this.directPeerConnection = this._createDirectPeerConnection();

            this.localStream.getTracks().forEach(track => {
                this.directPeerConnection.addTrack(track, this.localStream);
            });

            await this.directPeerConnection.setRemoteDescription(new RTCSessionDescription(offer));
            const answer = await this.directPeerConnection.createAnswer();
            await this.directPeerConnection.setLocalDescription(answer);

            this.socket.emit('call_response', {
                sender: this.currentUser,
                receiver: this.partnerName,
                status: 'accepted',
                answer: answer
            });

            this.audioPlayer.playChime('join');
            this.onCallStatusChange('Active Call');
        }

        declineDirectCall(caller) {
            this.audioPlayer.stopRingTone();
            if (this.socket && this.socket.connected) {
                this.socket.emit('call_response', {
                    sender: this.currentUser,
                    receiver: caller,
                    status: 'declined'
                });
            }
            this.cleanup();
        }

        endDirectCall() {
            this.audioPlayer.stopRingTone();
            if (this.socket && this.socket.connected && this.partnerName) {
                this.socket.emit('end_call', {
                    sender: this.currentUser,
                    receiver: this.partnerName
                });
            }
            this.audioPlayer.playChime('leave');
            this.cleanup();
            this.onCallEnded();
        }

        _createDirectPeerConnection() {
            const pc = new RTCPeerConnection(RTC_CONFIG);

            pc.onicecandidate = (event) => {
                if (event.candidate && this.socket && this.socket.connected) {
                    this.socket.emit('ice_candidate', {
                        sender: this.currentUser,
                        receiver: this.partnerName,
                        candidate: event.candidate
                    });
                }
            };

            pc.ontrack = (event) => {
                const remoteStream = event.streams[0];
                this.onRemoteStreamAdded('remote', remoteStream, this.partnerName);

                this._startAudioAnalysis('remote', remoteStream, (isSpeaking) => {
                    this.onSpeakingChange('remote', isSpeaking);
                });
            };

            pc.onconnectionstatechange = () => {
                if (pc.connectionState === 'connected') {
                    this.audioPlayer.stopRingTone();
                    this.onCallStatusChange('Active Call');
                } else if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
                    this.onCallStatusChange('Reconnecting...');
                } else if (pc.connectionState === 'closed') {
                    this.onCallStatusChange('Call Ended');
                }
            };

            return pc;
        }

        // ==========================================
        // Multi-Peer Mesh Group Huddle
        // ==========================================

        async joinGroupCall(roomName = 'team_chat', callType = 'video') {
            this.cleanup();
            this.callMode = 'group';
            this.currentRoom = roomName;
            this.callType = callType;

            this.onCallStatusChange('Joining Huddle...');
            await this.startLocalMedia({ video: callType === 'video', audio: true });

            this.audioPlayer.playChime('join');
            this.socket.emit('group_call_join', {
                room: roomName,
                username: this.currentUser
            });

            this.onCallStatusChange('Connected');
        }

        leaveGroupCall() {
            if (this.callMode === 'group' && this.socket && this.socket.connected) {
                this.socket.emit('group_call_leave', {
                    room: this.currentRoom
                });
            }
            this.audioPlayer.playChime('leave');
            this.cleanup();
            this.onCallEnded();
        }

        // ==========================================
        // Socket Signalling Handlers
        // ==========================================

        _setupSocketListeners() {
            if (!this.socket) return;

            // 1:1 Direct Signalling Responses
            this.socket.on('call_answered', async (data) => {
                if (this.callMode !== 'direct') return;

                this.audioPlayer.stopRingTone();
                if (data.status === 'accepted' && data.answer) {
                    try {
                        await this.directPeerConnection.setRemoteDescription(new RTCSessionDescription(data.answer));
                        this.audioPlayer.playChime('join');
                        this.onCallStatusChange('Active Call');
                    } catch (err) {
                        console.error('Error handling direct answer:', err);
                        this.endDirectCall();
                    }
                } else {
                    this.onCallStatusChange(`Call ${data.status}`);
                    this.cleanup();
                    this.onCallEnded();
                }
            });

            this.socket.on('new_ice_candidate', async (data) => {
                if (this.callMode === 'direct' && this.directPeerConnection) {
                    try {
                        await this.directPeerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
                    } catch (e) {
                        console.warn('Error adding direct ICE candidate:', e);
                    }
                }
            });

            this.socket.on('call_ended', () => {
                if (this.callMode === 'direct') {
                    this.audioPlayer.stopRingTone();
                    this.audioPlayer.playChime('leave');
                    this.cleanup();
                    this.onCallEnded();
                }
            });

            // Group Mesh Signalling Handlers
            this.socket.on('group_call_peers_list', async (data) => {
                if (this.callMode !== 'group') return;
                const peers = data.peers || [];

                // As the joiner, initiate an offer to every existing peer in the mesh
                for (const peerInfo of peers) {
                    await this._connectToMeshPeer(peerInfo.sid, peerInfo.username, true);
                    if (peerInfo.hand_raised) {
                        this.onHandChange(peerInfo.sid, true);
                    }
                }
            });

            this.socket.on('group_call_user_joined', async (data) => {
                if (this.callMode !== 'group') return;
                this.audioPlayer.playChime('join');
                // The new joiner will send us an offer; initialize peer record
                this._connectToMeshPeer(data.sid, data.username, false);
            });

            this.socket.on('group_call_signal', async (data) => {
                if (this.callMode !== 'group') return;
                const senderSid = data.sender_sid;
                const signalType = data.signal_type;
                const signalData = data.data;

                let peer = this.groupPeers.get(senderSid);
                if (!peer) {
                    peer = await this._connectToMeshPeer(senderSid, data.username, false);
                }

                if (signalType === 'offer') {
                    try {
                        await peer.pc.setRemoteDescription(new RTCSessionDescription(signalData));
                        const answer = await peer.pc.createAnswer();
                        await peer.pc.setLocalDescription(answer);

                        this.socket.emit('group_call_signal', {
                            target_sid: senderSid,
                            signal_type: 'answer',
                            data: answer
                        });
                    } catch (err) {
                        console.error('Error answering mesh peer offer:', err);
                    }
                } else if (signalType === 'answer') {
                    try {
                        await peer.pc.setRemoteDescription(new RTCSessionDescription(signalData));
                    } catch (err) {
                        console.error('Error setting mesh peer answer:', err);
                    }
                } else if (signalType === 'candidate') {
                    try {
                        await peer.pc.addIceCandidate(new RTCIceCandidate(signalData));
                    } catch (err) {
                        console.warn('Error adding mesh ICE candidate:', err);
                    }
                }
            });

            this.socket.on('group_call_user_left', (data) => {
                if (this.callMode !== 'group') return;
                this.audioPlayer.playChime('leave');
                this._removeMeshPeer(data.sid);
            });

            this.socket.on('group_call_hand_updated', (data) => {
                if (this.callMode !== 'group') return;
                if (data.sid !== this.socket.id && data.raised) {
                    this.audioPlayer.playChime('hand');
                }
                this.onHandChange(data.sid, data.raised);
            });
        }

        async _connectToMeshPeer(peerSid, username, isInitiator) {
            if (this.groupPeers.has(peerSid)) {
                return this.groupPeers.get(peerSid);
            }

            const pc = new RTCPeerConnection(RTC_CONFIG);
            const peerRecord = {
                pc,
                username,
                stream: null
            };
            this.groupPeers.set(peerSid, peerRecord);

            // Add local tracks to peer
            if (this.localStream) {
                this.localStream.getTracks().forEach(track => {
                    pc.addTrack(track, this.localStream);
                });
            }

            // Handle ICE candidates
            pc.onicecandidate = (event) => {
                if (event.candidate && this.socket && this.socket.connected) {
                    this.socket.emit('group_call_signal', {
                        target_sid: peerSid,
                        signal_type: 'candidate',
                        data: event.candidate
                    });
                }
            };

            // Handle incoming remote stream
            pc.ontrack = (event) => {
                const stream = event.streams[0];
                peerRecord.stream = stream;
                this.onRemoteStreamAdded(peerSid, stream, username);

                this._startAudioAnalysis(peerSid, stream, (isSpeaking) => {
                    this.onSpeakingChange(peerSid, isSpeaking);
                });
            };

            pc.onconnectionstatechange = () => {
                if (pc.connectionState === 'failed' || pc.connectionState === 'closed') {
                    this._removeMeshPeer(peerSid);
                }
            };

            if (isInitiator) {
                try {
                    const offer = await pc.createOffer();
                    await pc.setLocalDescription(offer);
                    this.socket.emit('group_call_signal', {
                        target_sid: peerSid,
                        signal_type: 'offer',
                        data: offer
                    });
                } catch (e) {
                    console.error('Failed to create mesh offer to:', peerSid, e);
                }
            }

            return peerRecord;
        }

        _removeMeshPeer(peerSid) {
            const peer = this.groupPeers.get(peerSid);
            if (peer) {
                if (peer.pc) {
                    peer.pc.close();
                }
                this._stopAudioAnalysis(peerSid);
                this.groupPeers.delete(peerSid);
                this.onRemoteStreamRemoved(peerSid);
            }
        }

        // ==========================================
        // Cleanup & Teardown
        // ==========================================

        _setupUnloadHandler() {
            window.addEventListener('beforeunload', () => {
                this.cleanup();
            });
            window.addEventListener('pagehide', () => {
                this.cleanup();
            });
        }

        cleanup() {
            this.audioPlayer.stopRingTone();

            // Stop local media
            if (this.localStream) {
                this.localStream.getTracks().forEach(track => track.stop());
                this.localStream = null;
            }
            if (this.localPreviewStream) {
                this.localPreviewStream.getTracks().forEach(track => track.stop());
                this.localPreviewStream = null;
            }
            if (this.screenStream) {
                this.screenStream.getTracks().forEach(track => track.stop());
                this.screenStream = null;
            }

            this.cameraTrack = null;
            this.micTrack = null;
            this.isScreenSharing = false;
            this.isHandRaised = false;

            // Close 1:1 connection
            if (this.directPeerConnection) {
                this.directPeerConnection.close();
                this.directPeerConnection = null;
            }

            // Close mesh group connections
            this.groupPeers.forEach(peer => {
                if (peer.pc) {
                    peer.pc.close();
                }
            });
            this.groupPeers.clear();

            // Clear audio analyzers and disconnect Web Audio nodes
            this.analysers.forEach(entry => {
                try {
                    if (entry.source) entry.source.disconnect();
                } catch (e) {}
                try {
                    if (entry.analyser) entry.analyser.disconnect();
                } catch (e) {}
            });
            this.analysers.clear();
            if (this.speechDetectionInterval) {
                clearInterval(this.speechDetectionInterval);
                this.speechDetectionInterval = null;
            }

            this.callMode = null;
            this.partnerName = null;
            this.currentRoom = null;
        }
    }

    // Export to global scope
    window.LanCallManager = LanCallManager;

})(window);
