import unittest
from flask import Flask, session
from flask_socketio import SocketIO, emit, join_room
from flask_socketio.test_client import SocketIOTestClient
import app as server_app

if not hasattr(SocketIOTestClient, 'sid'):
    SocketIOTestClient.sid = property(lambda self: self.socketio.server.manager.sid_from_eio_sid(self.eio_sid, '/'))

class TestVideoSignalling(unittest.TestCase):
    def setUp(self):
        self.app = server_app.app
        self.app.config['TESTING'] = True
        self.socketio = server_app.socketio
        self.socketio.manage_session = False
        # Reset state
        if hasattr(server_app, 'active_group_calls'):
            server_app.active_group_calls.clear()
        server_app.sid_to_username.clear()
        server_app.online_users.clear()

    def test_dm_call_signalling(self):
        client1 = self.socketio.test_client(self.app)
        client2 = self.socketio.test_client(self.app)

        server_app.sid_to_username[client1.sid] = "alice"
        server_app.sid_to_username[client2.sid] = "bob"
        server_app.online_users["alice"] = {"sid": client1.sid, "status": "online"}
        server_app.online_users["bob"] = {"sid": client2.sid, "status": "online"}

        room = server_app.get_dm_room("alice", "bob")
        client1.emit("join_dm", {"user1": "alice", "user2": "bob"})
        client2.emit("join_dm", {"user1": "alice", "user2": "bob"})

        # Test call_user with call_type
        client1.emit("call_user", {
            "sender": "alice",
            "receiver": "bob",
            "call_type": "video",
            "offer": {"type": "offer", "sdp": "dummy_sdp"}
        })
        received2 = client2.get_received()
        call_events = [e for e in received2 if e["name"] == "incoming_call"]
        self.assertTrue(len(call_events) >= 1)
        self.assertEqual(call_events[0]["args"][0]["call_type"], "video")
        self.assertEqual(call_events[0]["args"][0]["sender"], "alice")

    def test_group_call_join_and_leave(self):
        client1 = self.socketio.test_client(self.app)
        client2 = self.socketio.test_client(self.app)

        server_app.sid_to_username[client1.sid] = "alice"
        server_app.sid_to_username[client2.sid] = "bob"

        client1.emit("group_call_join", {"room": "team_chat", "username": "alice"})
        received1 = client1.get_received()
        peers_event = [e for e in received1 if e["name"] == "group_call_peers_list"]
        self.assertEqual(len(peers_event), 1)
        self.assertEqual(len(peers_event[0]["args"][0]["peers"]), 0)

        # Bob joins
        client2.emit("group_call_join", {"room": "team_chat", "username": "bob"})
        received2 = client2.get_received()
        peers_event2 = [e for e in received2 if e["name"] == "group_call_peers_list"]
        self.assertEqual(len(peers_event2), 1)
        self.assertEqual(len(peers_event2[0]["args"][0]["peers"]), 1)
        self.assertEqual(peers_event2[0]["args"][0]["peers"][0]["username"], "alice")

        # Bob leaves
        client2.emit("group_call_leave", {"room": "team_chat"})
        received1_after = client1.get_received()
        left_events = [e for e in received1_after if e["name"] == "group_call_user_left"]
        self.assertTrue(len(left_events) >= 1)
        self.assertEqual(left_events[0]["args"][0]["username"], "bob")

    def test_group_call_signal(self):
        client1 = self.socketio.test_client(self.app)
        client2 = self.socketio.test_client(self.app)

        server_app.sid_to_username[client1.sid] = "alice"
        server_app.sid_to_username[client2.sid] = "bob"

        client1.emit("group_call_join", {"room": "team_chat", "username": "alice"})
        client2.emit("group_call_join", {"room": "team_chat", "username": "bob"})

        client1.emit("group_call_signal", {
            "target_sid": client2.sid,
            "signal_type": "offer",
            "data": {"sdp": "dummy_offer"}
        })

        received2 = client2.get_received()
        signal_events = [e for e in received2 if e["name"] == "group_call_signal"]
        self.assertEqual(len(signal_events), 1)
        self.assertEqual(signal_events[0]["args"][0]["sender_sid"], client1.sid)
        self.assertEqual(signal_events[0]["args"][0]["signal_type"], "offer")
        self.assertEqual(signal_events[0]["args"][0]["data"], {"sdp": "dummy_offer"})

    def test_group_call_hand(self):
        client1 = self.socketio.test_client(self.app)
        server_app.sid_to_username[client1.sid] = "alice"
        client1.emit("group_call_join", {"room": "team_chat", "username": "alice"})

        client1.emit("group_call_hand", {"room": "team_chat", "raised": True})
        received = client1.get_received()
        hand_events = [e for e in received if e["name"] == "group_call_hand_updated"]
        self.assertEqual(len(hand_events), 1)
        self.assertTrue(hand_events[0]["args"][0]["raised"])
        self.assertEqual(hand_events[0]["args"][0]["sid"], client1.sid)

    def test_group_call_disconnect_cleanup(self):
        client1 = self.socketio.test_client(self.app)
        client2 = self.socketio.test_client(self.app)

        server_app.sid_to_username[client1.sid] = "alice"
        server_app.sid_to_username[client2.sid] = "bob"

        client1.emit("group_call_join", {"room": "team_chat", "username": "alice"})
        client2.emit("group_call_join", {"room": "team_chat", "username": "bob"})

        client2.disconnect()
        received1 = client1.get_received()
        left_events = [e for e in received1 if e["name"] == "group_call_user_left"]
        self.assertTrue(len(left_events) >= 1)
        self.assertEqual(left_events[0]["args"][0]["username"], "bob")

    def test_three_client_mesh_huddle(self):
        """Verify 3 clients joining a group huddle get correct peer lists."""
        client1 = self.socketio.test_client(self.app)
        client2 = self.socketio.test_client(self.app)
        client3 = self.socketio.test_client(self.app)

        server_app.sid_to_username[client1.sid] = "alice"
        server_app.sid_to_username[client2.sid] = "bob"
        server_app.sid_to_username[client3.sid] = "charlie"

        # Alice joins first
        client1.emit("group_call_join", {"room": "team_chat", "username": "alice"})
        r1 = client1.get_received()
        peers1 = [e for e in r1 if e["name"] == "group_call_peers_list"]
        self.assertEqual(len(peers1[0]["args"][0]["peers"]), 0)

        # Bob joins second
        client2.emit("group_call_join", {"room": "team_chat", "username": "bob"})
        r2 = client2.get_received()
        peers2 = [e for e in r2 if e["name"] == "group_call_peers_list"]
        self.assertEqual(len(peers2[0]["args"][0]["peers"]), 1)
        self.assertEqual(peers2[0]["args"][0]["peers"][0]["username"], "alice")

        # Alice should get user_joined for bob
        r1_after = client1.get_received()
        joined1 = [e for e in r1_after if e["name"] == "group_call_user_joined"]
        self.assertTrue(any(e["args"][0]["username"] == "bob" for e in joined1))

        # Charlie joins third
        client3.emit("group_call_join", {"room": "team_chat", "username": "charlie"})
        r3 = client3.get_received()
        peers3 = [e for e in r3 if e["name"] == "group_call_peers_list"]
        self.assertEqual(len(peers3[0]["args"][0]["peers"]), 2)
        peer_names = {p["username"] for p in peers3[0]["args"][0]["peers"]}
        self.assertEqual(peer_names, {"alice", "bob"})

    def test_group_call_status_count(self):
        """Verify group_call_status broadcasts correct participant count."""
        client1 = self.socketio.test_client(self.app)
        client2 = self.socketio.test_client(self.app)

        server_app.sid_to_username[client1.sid] = "alice"
        server_app.sid_to_username[client2.sid] = "bob"

        client1.emit("group_call_join", {"room": "team_chat", "username": "alice"})
        r1 = client1.get_received()
        status1 = [e for e in r1 if e["name"] == "group_call_status"]
        self.assertTrue(len(status1) >= 1)
        self.assertEqual(status1[-1]["args"][0]["count"], 1)

        client2.emit("group_call_join", {"room": "team_chat", "username": "bob"})
        r1_after = client1.get_received()
        status2 = [e for e in r1_after if e["name"] == "group_call_status"]
        self.assertTrue(len(status2) >= 1)
        self.assertEqual(status2[-1]["args"][0]["count"], 2)

        # Bob leaves
        client2.emit("group_call_leave", {"room": "team_chat"})
        r1_final = client1.get_received()
        status3 = [e for e in r1_final if e["name"] == "group_call_status"]
        self.assertTrue(len(status3) >= 1)
        self.assertEqual(status3[-1]["args"][0]["count"], 1)

    def test_dm_call_decline(self):
        """Verify declined 1:1 call sends proper status."""
        client1 = self.socketio.test_client(self.app)
        client2 = self.socketio.test_client(self.app)

        server_app.sid_to_username[client1.sid] = "alice"
        server_app.sid_to_username[client2.sid] = "bob"

        room = server_app.get_dm_room("alice", "bob")
        client1.emit("join_dm", {"user1": "alice", "user2": "bob"})
        client2.emit("join_dm", {"user1": "alice", "user2": "bob"})

        # Alice calls Bob
        client1.emit("call_user", {
            "sender": "alice",
            "receiver": "bob",
            "call_type": "audio",
            "offer": {"type": "offer", "sdp": "test"}
        })
        client2.get_received()  # clear

        # Bob declines
        client2.emit("call_response", {
            "sender": "bob",
            "receiver": "alice",
            "status": "declined"
        })
        r1 = client1.get_received()
        answered = [e for e in r1 if e["name"] == "call_answered"]
        self.assertTrue(len(answered) >= 1)
        self.assertEqual(answered[0]["args"][0]["status"], "declined")

    def test_dm_end_call(self):
        """Verify end_call event is relayed to the other party."""
        client1 = self.socketio.test_client(self.app)
        client2 = self.socketio.test_client(self.app)

        server_app.sid_to_username[client1.sid] = "alice"
        server_app.sid_to_username[client2.sid] = "bob"

        room = server_app.get_dm_room("alice", "bob")
        client1.emit("join_dm", {"user1": "alice", "user2": "bob"})
        client2.emit("join_dm", {"user1": "alice", "user2": "bob"})
        client2.get_received()  # clear

        client1.emit("end_call", {
            "sender": "alice",
            "receiver": "bob"
        })
        r2 = client2.get_received()
        ended = [e for e in r2 if e["name"] == "call_ended"]
        self.assertTrue(len(ended) >= 1)
        self.assertEqual(ended[0]["args"][0]["sender"], "alice")

    def test_group_hand_toggle_off(self):
        """Verify hand raise can be toggled back to False."""
        client1 = self.socketio.test_client(self.app)
        server_app.sid_to_username[client1.sid] = "alice"
        client1.emit("group_call_join", {"room": "team_chat", "username": "alice"})
        client1.get_received()  # clear

        # Raise hand
        client1.emit("group_call_hand", {"room": "team_chat", "raised": True})
        r1 = client1.get_received()
        hand1 = [e for e in r1 if e["name"] == "group_call_hand_updated"]
        self.assertTrue(hand1[0]["args"][0]["raised"])

        # Lower hand
        client1.emit("group_call_hand", {"room": "team_chat", "raised": False})
        r2 = client1.get_received()
        hand2 = [e for e in r2 if e["name"] == "group_call_hand_updated"]
        self.assertFalse(hand2[0]["args"][0]["raised"])

if __name__ == "__main__":
    unittest.main()
