from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, async_mode="threading")

@app.route("/")
def hello(): return "Hello SocketIO"

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5002, ssl_context=("cert.pem", "key.pem"))
