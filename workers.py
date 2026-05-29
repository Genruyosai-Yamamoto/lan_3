def upload_worker(upload_queue, upload_registry, socketio):

    while True:

        item = upload_queue.get()

        if item is None:
            break

        upload_id = item["id"]

        filename = item["filename"]

        uploader = item["uploader"]

        ip = item["ip"]

        try:

            socketio.emit("upload_update", {
                "id": upload_id,
                "filename": filename,
                "status": "done"
            })

            socketio.emit("file_update", {
                "event": "new_file",
                "filename": filename,
                "uploader": uploader,
                "ip": ip
            })

        except Exception as e:

            print("WORKER ERROR:", e)

            upload_registry[upload_id]["status"] = "failed"

        upload_queue.task_done()
