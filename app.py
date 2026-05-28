from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import os
from datetime import datetime
import queue
import threading
from flask_socketio import SocketIO, emit
import uuid
from workers import upload_worker
from utils import log_activity

app = Flask(__name__)
socketio = SocketIO(app)

UPLOAD_FOLDER = "uploads"
LOG_FILE = "logs/activity.log"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("logs", exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

online_users = {}
upload_status = {}
upload_queue = queue.Queue()

worker_thread = threading.Thread(
    target=upload_worker,
    args=(upload_queue, upload_status, socketio),
    daemon=True
)

worker_thread.start()

@app.route("/")
def index():
    files = os.listdir(UPLOAD_FOLDER)
    return render_template("index.html", files=files)

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
    log_activity("JOINED", data.get("name", "Anonymous"))


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return redirect(url_for("index"))

    file = request.files["file"]
    uploader = request.form.get("uploader", "anonymous")

    if file.filename == "":
        return redirect(url_for("index"))

    upload_id = str(uuid.uuid4())[:8]

    upload_status[upload_id] = {
        "filename": file.filename,
        "status": "queued",
        "uploader": uploader,
        "ip": request.remote_addr
    }

    upload_queue.put({
        "id": upload_id,
        "file": file,
        "uploader": uploader,
        "ip": request.remote_addr
    })

    return {
        "upload_id": upload_id,
        "status": "queued"
    }

@app.route("/download/<filename>")
def download_file(filename):
    log_activity("DOWNLOAD", filename)

    return send_from_directory(
        UPLOAD_FOLDER,
        filename,
        as_attachment=True
    )
    
@app.route("/upload/<upload_id>/status")
def upload_status(upload_id):
    status = upload_status.get(upload_id, {"status": "not_found"})
    return status

@app.route("/uploads")
def uploads_dashboard():
    return render_template("uploads.html", uploads=upload_status)





if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)