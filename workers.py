from datetime import datetime, timezone, UTC
import time

online_users = {}

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

def get_dm_room(user1, user2):

    users = sorted([user1, user2])

    return f"dm_{users[0]}_{users[1]}"

def cleanup_offline_users(online_users, socketio):

    while True:

        now = datetime.now(timezone.utc)

        dead_users = []

        for username, user in online_users.items():

            try:

                last_seen = datetime.fromisoformat(
                    user["last_seen"]
                )

                diff = (now - last_seen).total_seconds()

                if diff > 60:
                    dead_users.append(username)

            except Exception:
                dead_users.append(username)

        for username in dead_users:

            print(f"REMOVING STALE USER: {username}")

            del online_users[username]

        socketio.emit(
            "online_users",
            list(online_users.values())
        )

        time.sleep(10)

def now_iso():
    return datetime.now(timezone.utc).isoformat()