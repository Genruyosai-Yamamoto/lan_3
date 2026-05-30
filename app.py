from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, abort
import os
import queue
import threading
import uuid
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from data import db, Message, Reaction, PrivateMessage, Conversation, UserKey, PrivateReaction
from workers import upload_worker, get_dm_room
from utils import log_activity
from datetime import datetime, timezone, UTC


app = Flask(__name__)
app.secret_key = "lan-e2ee-secret-key-123456"
socketio = SocketIO(app)
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

online_users = {}

upload_registry = {}

upload_queue = queue.Queue()

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
    files = os.listdir(UPLOAD_FOLDER)
    return render_template("index.html", files=files)

# =========================
# SOCKET EVENTS
# =========================

@socketio.on("connect")
def handle_connect():

    sid = request.sid

    online_users[sid] = {
        "sid": sid,
        "ip": request.remote_addr,
        "status": "online"
    }

    emit("online_users", online_users, broadcast=True)

@socketio.on("disconnect")
def handle_disconnect():

    sid = request.sid

    if sid in online_users:
        del online_users[sid]

    emit("online_users", online_users, broadcast=True)

@socketio.on("user_online")
def handle_user_online(data):

    sid = request.sid

    online_users[sid] = {
        "sid": sid,
        "ip": request.remote_addr,
        "name": data.get("name", "Anonymous"),
        "status": "online"
    }

    emit("online_users", online_users, broadcast=True)

    try:
        log_activity("JOINED", data.get("name", "Anonymous"))
    except Exception as e:
        print("LOG ERROR:", e)


# =========================
# FILE UPLOAD
# =========================

@app.route("/upload", methods=["POST"])
def upload_file():

    if "file" not in request.files:
        return redirect(url_for("index"))

    file = request.files["file"]

    uploader = request.form.get("uploader", "anonymous")

    if file.filename == "":
        return redirect(url_for("index"))

    upload_id = str(uuid.uuid4())[:8]

    # 🔥 SAVE IMMEDIATELY (FAST)
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)

    file.save(filepath)

    # =========================
    # TRACK STATUS
    # =========================

    upload_registry[upload_id] = {
        "filename": file.filename,
        "status": "done",
        "uploader": uploader,
        "ip": request.remote_addr
    }

    # =========================
    # BACKGROUND TASKS ONLY
    # =========================

    upload_queue.put({
        "id": upload_id,
        "filename": file.filename,
        "uploader": uploader,
        "ip": request.remote_addr
    })

    return {
        "upload_id": upload_id,
        "status": "done"
    }

# =========================
# DOWNLOAD
# =========================

@app.route("/download/<filename>")
def download_file(filename):

    log_activity("DOWNLOAD", filename)

    return send_from_directory(
        UPLOAD_FOLDER,
        filename,
        as_attachment=True
    )

# =========================
# STATUS API
# =========================

@app.route("/upload/<upload_id>/status")
def get_upload_status():

    upload_id = request.view_args["upload_id"]

    status = upload_registry.get(
        upload_id,
        {"status": "not_found"}
    )

    return status

# =========================
# DASHBOARD
# =========================

@app.route("/uploads")
def uploads_dashboard():

    return render_template(
        "uploads.html",
        uploads=upload_registry
    )

@app.route("/chat")
def chat_page():

    messages = Message.query.order_by(Message.timestamp.asc()).all()
    return render_template("chat.html", messages=messages)

@app.route("/upload_audio", methods=["POST"])
def upload_audio():

    audio = request.files["audio"]

    filename = f"{uuid.uuid4()}.webm"

    filepath = os.path.join(
        "uploads/audio",
        filename
    )

    audio.save(filepath)

    msg = Message(
        user=request.form.get("user", "Anonymous"),
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
    return send_from_directory("uploads/audio", filename)

@socketio.on("send_message")
def handle_message(data):

    msg = Message(
        user=data.get("user", "Anonymous"),
        sender_sid=request.sid,
        ip_address=request.remote_addr,
        message_type="text",
        content=data.get("text")
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
    

@socketio.on("edit_message")
def handle_edit_message(data):

    message_id = data.get("message_id")
    new_content = data.get("content")

    msg = db.session.get(Message, message_id)

    if not msg:
        return

    if msg.deleted:
        return

    if msg.message_type != "text":
        return

    # Owner verification
    if msg.sender_sid != request.sid:
        emit("error", {
            "message": "You can only edit your own messages."
        })
        return

    msg.content = new_content.strip()
    msg.edited = True
    msg.edited_at = datetime.now(timezone.utc)

    db.session.commit()

    socketio.emit(
        "message_edited",
        {
            "id": msg.id,
            "content": msg.content,
            "edited": True,
            "edited_at": msg.edited_at.strftime("%H:%M")
        }
    )

@socketio.on("delete_message")
def handle_delete_message(data):

    message_id = data.get("message_id")
    username = data.get("user")

    msg = db.session.get(Message, message_id)

    if not msg:
        return

    if msg.sender_sid != request.sid:
        emit("error", {
            "message": "You can only delete your own messages."
        })
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
        message_id=message_id,
        user=username,
        emoji=emoji
    ).first()

    if existing:
        return

    reaction = Reaction(
        message_id=message_id,
        user=username,
        emoji=emoji
    )

    db.session.add(reaction)
    db.session.commit()

    socketio.emit(
        "reaction_added",
        {
            "message_id": message_id,
            "emoji": emoji,
            "user": username
        }
    )

@socketio.on("remove_reaction")
def handle_remove_reaction(data):

    reaction = Reaction.query.filter_by(
        message_id=data["message_id"],
        user=data["user"],
        emoji=data["emoji"]
    ).first()

    if not reaction:
        return

    db.session.delete(reaction)
    db.session.commit()

    socketio.emit(
        "reaction_removed",
        {
            "message_id": data["message_id"],
            "emoji": data["emoji"],
            "user": data["user"]
        }
    )

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
    user_key = UserKey.query.filter_by(username=username).first()
    if not user_key:
        return {"error": "User public key not found"}, 404
    return {"username": username, "public_key": user_key.public_key}

@app.route("/upload_private_audio", methods=["POST"])
def upload_private_audio():
    audio = request.files["audio"]
    sender = request.form.get("sender")
    receiver = request.form.get("receiver")
    conversation_id = request.form.get("conversation_id")

    if not conversation_id:
        return {"error": "Missing conversation_id"}, 400

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
    socketio.emit(
        "new_private_message",
        {
            "id": msg.id,
            "sender": msg.sender,
            "receiver": msg.receiver,
            "type": msg.message_type,
            "content": msg.content,
            "time": msg.timestamp.strftime("%H:%M")
        },
        room=room
    )
    return {"success": True}

@app.route("/dm")
def dm():
    username = session.get("username") or request.cookies.get("username")
    if username and not session.get("username"):
        session["username"] = username

    online = list(online_users.values())

    # remove self from list
    if username:
        online = [u for u in online if u.get("name") != username]

    files = os.listdir(UPLOAD_FOLDER)
    return render_template(
        "dm.html",
        files=files,
        online_users=online,
        user=username
    )

@app.route("/dm/<int:conversation_id>")
def dm_chat(conversation_id):
    username = session.get("username") or request.cookies.get("username")
    if username and not session.get("username"):
        session["username"] = username

    if not username:
        return redirect(url_for("index"))

    convo = Conversation.query.get(conversation_id)
    if not convo:
        return abort(404)

    # 🔒 security: only participants can access
    if username not in [convo.user1, convo.user2]:
        return abort(403)

    messages = PrivateMessage.query.filter_by(
        conversation_id=conversation_id
    ).order_by(PrivateMessage.timestamp.asc()).all()

    partner = convo.user2 if convo.user1 == username else convo.user1

    # Load file lists if required by the page structure
    files = os.listdir(UPLOAD_FOLDER)

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
    username = session.get("username") or request.cookies.get("username")
    if username and not session.get("username"):
        session["username"] = username

    if not username:
        return redirect(url_for("index"))

    # check if conversation already exists
    convo = Conversation.query.filter(
        ((Conversation.user1 == username) & (Conversation.user2 == target_user)) |
        ((Conversation.user1 == target_user) & (Conversation.user2 == username))
    ).first()

    # create if not exists
    if not convo:
        convo = Conversation(
            user1=username,
            user2=target_user
        )
        db.session.add(convo)
        db.session.commit()

    return redirect(url_for("dm_chat", conversation_id=convo.id))

@socketio.on("typing")
def typing(data):
    room = get_dm_room(
        data["sender"],
        data["receiver"]
    )
    emit(
        "user_typing",
        {
            "user": data["sender"]
        },
        room=room,
        include_self=False
    )

@socketio.on("join_dm")
def join_dm(data):
    room = get_dm_room(
        data["user1"],
        data["user2"]
    )
    join_room(room)

@socketio.on("send_private_message")
def send_private_message(data):
    room = get_dm_room(
        data["sender"],
        data["receiver"]
    )
    msg = PrivateMessage(
        conversation_id=data.get("conversation_id") or 1,  # fallback if needed, but client should send it
        sender=data["sender"],
        receiver=data["receiver"],
        message_type="text",
        content=data["message"]
    )
    db.session.add(msg)
    db.session.commit()

    # If the conversation_id is not passed, let's fetch it
    if not data.get("conversation_id"):
        convo = Conversation.query.filter(
            ((Conversation.user1 == msg.sender) & (Conversation.user2 == msg.receiver)) |
            ((Conversation.user1 == msg.receiver) & (Conversation.user2 == msg.sender))
        ).first()
        if convo:
            msg.conversation_id = convo.id
            db.session.commit()

    socketio.emit(
        "new_private_message",
        {
            "id": msg.id,
            "sender": msg.sender,
            "receiver": msg.receiver,
            "content": msg.content,
            "time": msg.timestamp.strftime("%H:%M")
        },
        room=room
    )

@socketio.on("edit_private_message")
def handle_edit_private_message(data):
    message_id = data.get("message_id")
    new_content = data.get("content")
    
    msg = db.session.get(PrivateMessage, message_id)
    if not msg:
        return
        
    username = session.get("username") or request.cookies.get("username")
    if msg.sender != username:
        emit("error", {"message": "You can only edit your own messages."})
        return
        
    msg.content = new_content.strip()
    msg.edited = True
    db.session.commit()
    
    room = get_dm_room(msg.sender, msg.receiver)
    socketio.emit(
        "private_message_edited",
        {
            "id": msg.id,
            "content": msg.content,
            "edited": True
        },
        room=room
    )

@socketio.on("delete_private_message")
def handle_delete_private_message(data):
    message_id = data.get("message_id")
    
    msg = db.session.get(PrivateMessage, message_id)
    if not msg:
        return
        
    username = session.get("username") or request.cookies.get("username")
    if msg.sender != username:
        emit("error", {"message": "You can only delete your own messages."})
        return
        
    msg.deleted = True
    db.session.commit()
    
    room = get_dm_room(msg.sender, msg.receiver)
    socketio.emit(
        "private_message_deleted",
        {
            "id": msg.id,
            "deleted": True
        },
        room=room
    )

@socketio.on("add_private_reaction")
def handle_private_reaction(data):
    message_id = data.get("message_id")
    emoji = data.get("emoji")
    username = data.get("user")

    msg = db.session.get(PrivateMessage, message_id)
    if not msg:
        return

    existing = PrivateReaction.query.filter_by(
        message_id=message_id,
        user=username,
        emoji=emoji
    ).first()

    if existing:
        return

    reaction = PrivateReaction(
        message_id=message_id,
        user=username,
        emoji=emoji
    )
    db.session.add(reaction)
    db.session.commit()

    room = get_dm_room(msg.sender, msg.receiver)
    socketio.emit(
        "private_reaction_added",
        {
            "message_id": message_id,
            "emoji": emoji,
            "user": username
        },
        room=room
    )

@socketio.on("remove_private_reaction")
def handle_remove_private_reaction(data):
    message_id = data.get("message_id")
    emoji = data.get("emoji")
    username = data.get("user")

    msg = db.session.get(PrivateMessage, message_id)
    if not msg:
        return

    reaction = PrivateReaction.query.filter_by(
        message_id=message_id,
        user=username,
        emoji=emoji
    ).first()

    if not reaction:
        return

    db.session.delete(reaction)
    db.session.commit()

    room = get_dm_room(msg.sender, msg.receiver)
    socketio.emit(
        "private_reaction_removed",
        {
            "message_id": message_id,
            "emoji": emoji,
            "user": username
        },
        room=room
    )


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True
    )

