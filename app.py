from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import os
import queue
import threading
import uuid
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from data import db, Message
from workers import upload_worker
from utils import log_activity

app = Flask(__name__)
socketio = SocketIO(app)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("logs", exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

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

@socketio.on("send_message")
def handle_message(data):

    msg = Message(
        user=data.get("user", "Anonymous"),
        text=data.get("text")
    )

    db.session.add(msg)
    db.session.commit()

    socketio.emit("new_message", {
        "user": msg.user,
        "text": msg.text,
        "time": msg.timestamp.strftime("%H:%M")
    })
    
# =========================
# RUN SERVER
# =========================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True
    )

