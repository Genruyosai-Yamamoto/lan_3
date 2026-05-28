import os

UPLOAD_FOLDER = "uploads"

def upload_worker(upload_queue, upload_status, socketio):
    while True:
        item = upload_queue.get()

        if item is None:
            break

        upload_id = item["id"]
        file = item["file"]
        uploader = item["uploader"]
        ip = item["ip"]

        upload_status[upload_id]["status"] = "uploading"

        socketio.emit("upload_update", {
            "id": upload_id,
            "filename": file.filename,
            "status": "uploading"
        })

        try:
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.stream.save(filepath)

            upload_status[upload_id]["status"] = "done"

            socketio.emit("upload_update", {
                "id": upload_id,
                "filename": file.filename,
                "status": "done"
            })

            socketio.emit("file_update", {
                "event": "new_file",
                "filename": file.filename,
                "uploader": uploader,
                "ip": ip
            })

        except Exception:
            upload_status[upload_id]["status"] = "failed"

        upload_queue.task_done()