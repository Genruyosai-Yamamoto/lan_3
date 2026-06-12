from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, abort
import os
import queue
import threading
import uuid
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from data import db, Message, Reaction, PrivateMessage, Conversation, UserKey, PrivateReaction
from workers import upload_worker, get_dm_room, cleanup_offline_users, now_iso
from utils import log_activity
from datetime import datetime, timezone, UTC
import time
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.secret_key = "ernflikwenfjbelirgjernglijiirjlie"

# FIX 1: Explicit CORS + longer ping timeouts prevent LAN disconnects
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
    async_mode="threading"
)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

UPLOAD_FOLDER = "uploads"
AUDIO_FOLDER = "uploads/audio"

os.makedirs(AUDIO_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("logs", exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["AUDIO_FOLDER"] = AUDIO_FOLDER

# =========================
# STORAGE
# =========================

online_users = {}        # username -> {name, sid, ip, status, last_seen}
# FIX 2: Reverse lookup dict for O(1) disconnect instead of scanning all users
sid_to_username = {}     # sid -> username

upload_registry = {}
upload_queue = queue.Queue()


# =========================
# HELPERS
# =========================

# FIX 3: Only list real files, skip subdirectories like "audio"
def get_upload_files():
    try:
        items = os.listdir(UPLOAD_FOLDER)
        return [
            f for f in items
            if os.path.isfile(os.path.join(UPLOAD_FOLDER, f))
        ]
    except OSError:
        return []


# =========================
# BACKGROUND WORKER
# =========================

worker_thread = threading.Thread(
    target=upload_worker,
    args=(upload_queue, upload_registry, socketio),
    daemon=True
)
worker_thread.start()


# =========================
# ROUTES
# =========================

@app.route("/")
def index():
    files = get_upload_files()
    # FIX 4: Pass display_files explicitly so the template doesn't use
    #         an undefined variable before the {% set %} line
    return render_template("index.html", files=files, display_files=files)


@app.route("/api/file_count")
def file_count():
    return {"count": len(get_upload_files())}


# =========================
# SOCKET EVENTS
# =========================

@socketio.on("connect")
def handle_connect(auth=None):
    print(f"CONNECTED: {request.sid}")


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid

    # FIX 5: O(1) lookup via sid_to_username instead of iterating all users
    username = sid_to_username.pop(sid, None)

    if username and username in online_users:
        # Only remove if the SID still matches — prevents deleting a
        # user who already reconnected with a new SID
        if online_users[username].get("sid") == sid:
            del online_users[username]

    print(f"DISCONNECTED: {username or 'unknown'} (SID: {sid})")
    print("ONLINE USERS:", online_users)
    print("----------------")

    socketio.emit("online_users", list(online_users.values()))


@socketio.on("user_online")
def handle_user_online(data):
    username = data.get("name", "").strip()
    if not username:
        return

    # FIX 6: Reject duplicate usernames from another session
    if username in online_users and online_users[username].get("sid") != request.sid:
        emit("username_taken", {"username": username})
        return

    # FIX 7: Clean stale SID mapping from previous session of this user
    old_sid = online_users.get(username, {}).get("sid")
    if old_sid and old_sid != request.sid and old_sid in sid_to_username:
        del sid_to_username[old_sid]

    online_users[username] = {
        "name": username,
        "sid": request.sid,
        "ip": request.remote_addr,
        "status": "online",
        "last_seen": now_iso()
    }

    sid_to_username[request.sid] = username

    print("ONLINE USERS:", online_users)
    print("----------------")

    socketio.emit("online_users", list(online_users.values()))


@socketio.on("heartbeat")
def handle_heartbeat(data):
    username = data.get("name", "").strip()
    if username and username in online_users:
        online_users[username]["last_seen"] = now_iso()
        online_users[username]["sid"] = request.sid
        online_users[username]["status"] = "online"
        # FIX 8: Keep sid_to_username in sync on every heartbeat
        sid_to_username[request.sid] = username


# =========================
# FILE UPLOAD
# =========================

@app.route("/upload", methods=["POST"])
def upload_file():
    # FIX 9: Return JSON errors instead of redirect (fetch can't handle redirects)
    if "file" not in request.files:
        return {"error": "No file provided"}, 400

    file = request.files["file"]
    uploader = request.form.get("uploader", "anonymous")

    if file.filename == "":
        return {"error": "No filename"}, 400

    upload_id = str(uuid.uuid4())[:8]

    # Security fix: prevent directory traversal/arbitrary file upload writing
    filename = secure_filename(file.filename)
    if not filename:
        return {"error": "Invalid filename"}, 400
        
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    upload_registry[upload_id] = {
        "filename": filename,
        "status": "done",
        "uploader": uploader,
        "ip": request.remote_addr
    }

    upload_queue.put({
        "id": upload_id,
        "filename": filename,
        "uploader": uploader,
        "ip": request.remote_addr
    })

    return {
        "upload_id": upload_id,
        "status": "done",
        "filename": filename
    }


# =========================
# DOWNLOAD
# =========================

@app.route("/download/<filename>")
def download_file(filename):
    # Security fix: prevent path traversal attacks on file downloads
    filename = secure_filename(filename)
    log_activity("DOWNLOAD", filename)
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)


# =========================
# STATUS API
# =========================

@app.route("/upload/<upload_id>/status")
def get_upload_status(upload_id):
    return upload_registry.get(upload_id, {"status": "not_found"})


# =========================
# DASHBOARD
# =========================

@app.route("/uploads")
def uploads_dashboard():
    return render_template("uploads.html", uploads=upload_registry)


@app.route("/chat")
def chat_page():
    messages = Message.query.order_by(Message.timestamp.asc()).all()
    return render_template("chat.html", messages=messages)


@app.route("/upload_audio", methods=["POST"])
def upload_audio():
    # Security check: authorize user via session
    username = session.get("username")
    if not username or request.form.get("user") != username:
        return {"error": "Unauthorized"}, 403

    audio = request.files["audio"]
    filename = f"{uuid.uuid4()}.webm"
    filepath = os.path.join("uploads/audio", filename)
    audio.save(filepath)

    msg = Message(
        user=username,
        sender_sid=request.form.get("sid"),
        ip_address=request.remote_addr,
        message_type="audio",
        content=filepath
    )
    db.session.add(msg)
    db.session.commit()

    socketio.emit("new_message", {
        "id": msg.id,
        "user": msg.user,
        "type": msg.message_type,
        "content": msg.content,
        "time": msg.timestamp.strftime("%H:%M")
    })

    return {"success": True}


@app.route("/audio/<filename>")
def get_audio(filename):
    filename = secure_filename(filename)
    return send_from_directory("uploads/audio", filename)


@socketio.on("send_message")
def handle_message(data):
    msg = Message(
        user=data.get("user", "Anonymous"),
        sender_sid=request.sid,
        ip_address=request.remote_addr,
        message_type="text",
        content=data.get("text"),
        reply_to_id=data.get("reply_to_id")
    )
    db.session.add(msg)
    db.session.commit()

    socketio.emit("new_message", {
        "id": msg.id,
        "user": msg.user,
        "type": msg.message_type,
        "content": msg.content,
        "time": msg.timestamp.strftime("%H:%M"),
        "reply_to_id": msg.reply_to_id,
        "reply_to_user": msg.reply_to.user if msg.reply_to else None,
        "reply_to_content": msg.reply_to.content if msg.reply_to else None
    })


@socketio.on("edit_message")
def handle_edit_message(data):
    message_id = data.get("message_id")
    new_content = data.get("content")

    msg = db.session.get(Message, message_id)
    if not msg or msg.deleted or msg.message_type != "text":
        return

    if msg.sender_sid != request.sid:
        emit("error", {"message": "You can only edit your own messages."})
        return

    msg.content = new_content.strip()
    msg.edited = True
    msg.edited_at = datetime.now(timezone.utc)
    db.session.commit()

    socketio.emit("message_edited", {
        "id": msg.id,
        "content": msg.content,
        "edited": True,
        "edited_at": msg.edited_at.strftime("%H:%M")
    })


@socketio.on("delete_message")
def handle_delete_message(data):
    message_id = data.get("message_id")
    msg = db.session.get(Message, message_id)
    if not msg:
        return

    if msg.sender_sid != request.sid:
        emit("error", {"message": "You can only delete your own messages."})
        return

    msg.deleted = True
    msg.deleted_at = datetime.now(timezone.utc)
    db.session.commit()

    socketio.emit("message_deleted", {
        "id": msg.id,
        "deleted": True,
        "deleted_at": msg.deleted_at.strftime("%H:%M")
    })


@socketio.on("add_reaction")
def handle_reaction(data):
    message_id = data.get("message_id")
    emoji = data.get("emoji")
    username = data.get("user")

    existing = Reaction.query.filter_by(
        message_id=message_id, user=username, emoji=emoji
    ).first()
    if existing:
        return

    reaction = Reaction(message_id=message_id, user=username, emoji=emoji)
    db.session.add(reaction)
    db.session.commit()

    socketio.emit("reaction_added", {
        "message_id": message_id, "emoji": emoji, "user": username
    })


@socketio.on("remove_reaction")
def handle_remove_reaction(data):
    reaction = Reaction.query.filter_by(
        message_id=data["message_id"], user=data["user"], emoji=data["emoji"]
    ).first()
    if not reaction:
        return

    db.session.delete(reaction)
    db.session.commit()

    socketio.emit("reaction_removed", {
        "message_id": data["message_id"], "emoji": data["emoji"], "user": data["user"]
    })


@app.route("/set_username", methods=["POST"])
def set_username():
    data = request.json or {}
    username = data.get("username")
    if username:
        session["username"] = username
        return {"success": True}
    return {"success": False, "error": "Username is required"}, 400


@app.route("/api/save_public_key", methods=["POST"])
def save_public_key():
    data = request.json or {}
    username = data.get("username")
    public_key = data.get("public_key")
    if not username or not public_key:
        return {"error": "Missing username or public_key"}, 400

    # Security fix: prevent public key hijacking/spoofing of other users
    session_username = session.get("username")
    if not session_username or session_username != username:
        return {"error": "Unauthorized to save key for another user"}, 403

    user_key = UserKey.query.filter_by(username=username).first()
    if not user_key:
        user_key = UserKey(username=username, public_key=public_key)
        db.session.add(user_key)
    else:
        user_key.public_key = public_key
    db.session.commit()
    return {"success": True}


@app.route("/api/get_public_key/<username>")
def get_public_key(username):
    # Security fix: restrict keys fetch to authenticated clients
    if not session.get("username"):
        return {"error": "Authentication required"}, 401
    user_key = UserKey.query.filter_by(username=username).first()
    if not user_key:
        return {"error": "User public key not found"}, 404
    return {"username": username, "public_key": user_key.public_key}


@app.route("/upload_private_audio", methods=["POST"])
def upload_private_audio():
    sender = request.form.get("sender")
    receiver = request.form.get("receiver")
    conversation_id = request.form.get("conversation_id")

    # Security check: authorize the sender
    session_username = session.get("username")
    if not session_username or sender != session_username:
        return {"error": "Unauthorized"}, 403

    if not conversation_id:
        return {"error": "Missing conversation_id"}, 400

    audio = request.files["audio"]
    filename = f"{uuid.uuid4()}.webm"
    filepath = os.path.join("uploads/audio", filename)
    audio.save(filepath)

    msg = PrivateMessage(
        conversation_id=int(conversation_id),
        sender=sender,
        receiver=receiver,
        message_type="audio",
        content=filepath
    )
    db.session.add(msg)
    db.session.commit()

    room = get_dm_room(sender, receiver)
    socketio.emit("new_private_message", {
        "id": msg.id,
        "sender": msg.sender,
        "receiver": msg.receiver,
        "type": msg.message_type,
        "content": msg.content,
        "time": msg.timestamp.strftime("%H:%M")
    }, room=room)
    return {"success": True}


@app.route("/dm")
def dm():
    # Security fix: only use cryptographically signed session, no insecure cookies
    username = session.get("username")
    if not username:
        return redirect(url_for("index"))

    online = list(online_users.values())
    online = [u for u in online if u.get("name") != username]

    files = get_upload_files()
    return render_template("dm.html", files=files, online_users=online, user=username)


@app.route("/dm/<int:conversation_id>")
def dm_chat(conversation_id):
    # Security fix: only use signed session
    username = session.get("username")
    if not username:
        return redirect(url_for("index"))

    convo = db.session.get(Conversation, conversation_id)
    if not convo:
        return abort(404)
    if username not in [convo.user1, convo.user2]:
        return abort(403)

    messages = PrivateMessage.query.filter_by(
        conversation_id=conversation_id
    ).order_by(PrivateMessage.timestamp.asc()).all()

    partner = convo.user2 if convo.user1 == username else convo.user1
    files = get_upload_files()

    return render_template(
        "dm.html",
        messages=messages,
        conversation=convo,
        partner=partner,
        user=username,
        files=files
    )


@app.route("/dm/start_dm/<target_user>")
def start_dm(target_user):
    # Security fix: only use signed session
    username = session.get("username")
    if not username:
        return redirect(url_for("index"))

    convo = Conversation.query.filter(
        ((Conversation.user1 == username) & (Conversation.user2 == target_user)) |
        ((Conversation.user1 == target_user) & (Conversation.user2 == username))
    ).first()

    if not convo:
        convo = Conversation(user1=username, user2=target_user)
        db.session.add(convo)
        db.session.commit()

    return redirect(url_for("dm_chat", conversation_id=convo.id))


@socketio.on("typing")
def typing(data):
    username = sid_to_username.get(request.sid) or session.get("username")
    if not username or data.get("sender") != username:
        return
    room = get_dm_room(data["sender"], data["receiver"])
    emit("user_typing", {"user": data["sender"]}, room=room, include_self=False)


@socketio.on("join_dm")
def join_dm(data):
    username = sid_to_username.get(request.sid) or session.get("username")
    print(f"DEBUG JOIN_DM: session/sid username={username}, data={data}", flush=True)
    # Security fix: prevent users from joining other users' private DM rooms
    if not username or username not in [data.get("user1"), data.get("user2")]:
        print(f"DEBUG JOIN_DM: check failed! username={username}, user1={data.get('user1')}, user2={data.get('user2')}", flush=True)
        return
    room = get_dm_room(data["user1"], data["user2"])
    join_room(room)
    print(f"DEBUG JOIN_DM: joined room {room}", flush=True)


@socketio.on("send_private_message")
def send_private_message(data):
    username = sid_to_username.get(request.sid) or session.get("username")
    print(f"DEBUG SEND_PRIVATE_MESSAGE: session/sid username={username}, data={data}", flush=True)
    # Security fix: prevent message sender spoofing
    if not username or data.get("sender") != username:
        print(f"DEBUG SEND_PRIVATE_MESSAGE: spoofing check failed! username={username}, sender={data.get('sender')}", flush=True)
        return

    room = get_dm_room(data["sender"], data["receiver"])
    msg = PrivateMessage(
        conversation_id=data.get("conversation_id") or 1,
        sender=data["sender"],
        receiver=data["receiver"],
        message_type="text",
        content=data["message"],
        reply_to_id=data.get("reply_to_id")
    )
    db.session.add(msg)
    db.session.commit()

    if not data.get("conversation_id"):
        convo = Conversation.query.filter(
            ((Conversation.user1 == msg.sender) & (Conversation.user2 == msg.receiver)) |
            ((Conversation.user1 == msg.receiver) & (Conversation.user2 == msg.sender))
        ).first()
        if convo:
            msg.conversation_id = convo.id
            db.session.commit()

    print(f"DEBUG SEND_PRIVATE_MESSAGE: emitting to room {room}", flush=True)
    emit("new_private_message", {
        "id": msg.id,
        "sender": msg.sender,
        "receiver": msg.receiver,
        "content": msg.content,
        "time": msg.timestamp.strftime("%H:%M"),
        "reply_to_id": msg.reply_to_id,
        "reply_to_user": msg.reply_to.sender if msg.reply_to else None,
        "reply_to_content": msg.reply_to.content if msg.reply_to else None
    }, room=room)


@socketio.on("edit_private_message")
def handle_edit_private_message(data):
    message_id = data.get("message_id")
    new_content = data.get("content")

    msg = db.session.get(PrivateMessage, message_id)
    if not msg:
        return

    # Security fix: authenticate sender from session
    username = sid_to_username.get(request.sid) or session.get("username")
    if not username or msg.sender != username:
        emit("error", {"message": "You can only edit your own messages."})
        return

    msg.content = new_content.strip()
    msg.edited = True
    db.session.commit()

    room = get_dm_room(msg.sender, msg.receiver)
    emit("private_message_edited", {
        "id": msg.id, "content": msg.content, "edited": True
    }, room=room)


@socketio.on("delete_private_message")
def handle_delete_private_message(data):
    message_id = data.get("message_id")
    msg = db.session.get(PrivateMessage, message_id)
    if not msg:
        return

    # Security fix: authenticate sender from session
    username = sid_to_username.get(request.sid) or session.get("username")
    if not username or msg.sender != username:
        emit("error", {"message": "You can only delete your own messages."})
        return

    msg.deleted = True
    db.session.commit()

    room = get_dm_room(msg.sender, msg.receiver)
    emit("private_message_deleted", {
        "id": msg.id, "deleted": True
    }, room=room)


@socketio.on("add_private_reaction")
def handle_private_reaction(data):
    message_id = data.get("message_id")
    emoji = data.get("emoji")
    username = sid_to_username.get(request.sid) or session.get("username")

    if not username or data.get("user") != username:
        return

    msg = db.session.get(PrivateMessage, message_id)
    if not msg or username not in [msg.sender, msg.receiver]:
        return

    existing = PrivateReaction.query.filter_by(
        message_id=message_id, user=username, emoji=emoji
    ).first()
    if existing:
        return

    reaction = PrivateReaction(
        message_id=message_id, user=username, emoji=emoji
    )
    db.session.add(reaction)
    db.session.commit()

    room = get_dm_room(msg.sender, msg.receiver)
    emit("private_reaction_added", {
        "message_id": message_id, "emoji": emoji, "user": username
    }, room=room)


@socketio.on("remove_private_reaction")
def handle_remove_private_reaction(data):
    message_id = data.get("message_id")
    emoji = data.get("emoji")
    username = sid_to_username.get(request.sid) or session.get("username")

    if not username or data.get("user") != username:
        return

    msg = db.session.get(PrivateMessage, message_id)
    if not msg or username not in [msg.sender, msg.receiver]:
        return

    reaction = PrivateReaction.query.filter_by(
        message_id=message_id, user=username, emoji=emoji
    ).first()
    if not reaction:
        return

    db.session.delete(reaction)
    db.session.commit()

    room = get_dm_room(msg.sender, msg.receiver)
    emit("private_reaction_removed", {
        "message_id": message_id, "emoji": emoji, "user": username
    }, room=room)


# =========================
# WEBRTC SIGNALLING FOR VOICE CALLS
# =========================

@socketio.on("call_user")
def handle_call_user(data):
    username = sid_to_username.get(request.sid) or session.get("username")
    if not username or data.get("sender") != username:
        return
    room = get_dm_room(data["sender"], data["receiver"])
    emit("incoming_call", {
        "sender": data["sender"],
        "offer": data["offer"]
    }, room=room, include_self=False)


@socketio.on("call_response")
def handle_call_response(data):
    username = sid_to_username.get(request.sid) or session.get("username")
    if not username or data.get("sender") != username:
        return
    room = get_dm_room(data["sender"], data["receiver"])
    emit("call_answered", {
        "receiver": data["sender"],
        "answer": data.get("answer"),
        "status": data["status"]
    }, room=room, include_self=False)


@socketio.on("ice_candidate")
def handle_ice_candidate(data):
    username = sid_to_username.get(request.sid) or session.get("username")
    if not username or data.get("sender") != username:
        return
    room = get_dm_room(data["sender"], data["receiver"])
    emit("new_ice_candidate", {
        "sender": data["sender"],
        "candidate": data["candidate"]
    }, room=room, include_self=False)


@socketio.on("end_call")
def handle_end_call(data):
    username = sid_to_username.get(request.sid) or session.get("username")
    if not username or data.get("sender") != username:
        return
    room = get_dm_room(data["sender"], data["receiver"])
    emit("call_ended", {
        "sender": data["sender"]
    }, room=room, include_self=False)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # Fallback database migrations: add reply_to_id columns to existing databases
        try:
            db.session.execute(db.text("ALTER TABLE message ADD COLUMN reply_to_id INTEGER REFERENCES message(id)"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(db.text("ALTER TABLE private_message ADD COLUMN reply_to_id INTEGER REFERENCES private_message(id)"))
            db.session.commit()
        except Exception:
            db.session.rollback()

    socketio.start_background_task(cleanup_offline_users, online_users, socketio)

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False   
    )