import unittest
from flask import session
from flask_socketio.test_client import SocketIOTestClient
import app as server_app
from data import db, UserKey

if not hasattr(SocketIOTestClient, 'sid'):
    SocketIOTestClient.sid = property(lambda self: self.socketio.server.manager.sid_from_eio_sid(self.eio_sid, '/'))

class TestCryptoEndpoints(unittest.TestCase):
    def setUp(self):
        self.app = server_app.app
        self.app.config['TESTING'] = True
        self.socketio = server_app.socketio
        self.client = self.app.test_client()

    def test_save_and_get_public_key_with_session(self):
        with self.client.session_transaction() as sess:
            sess['username'] = 'alice_test'

        # Save public key
        res = self.client.post('/api/save_public_key', json={
            'username': 'alice_test',
            'public_key': '{"kty":"EC","crv":"P-256","x":"testx","y":"testy"}'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get('success'))

        # Get public key
        get_res = self.client.get('/api/get_public_key/alice_test')
        self.assertEqual(get_res.status_code, 200)
        data = get_res.get_json()
        self.assertEqual(data.get('username'), 'alice_test')
        self.assertIn('testx', data.get('public_key'))

    def test_save_and_get_public_key_with_cookie_sync(self):
        # Client without session, but with username cookie
        self.client.set_cookie('username', 'bob_test')

        res = self.client.post('/api/save_public_key', json={
            'username': 'bob_test',
            'public_key': '{"kty":"EC","crv":"P-256","x":"bobx","y":"boby"}'
        })
        self.assertEqual(res.status_code, 200)

        get_res = self.client.get('/api/get_public_key/bob_test')
        self.assertEqual(get_res.status_code, 200)
        data = get_res.get_json()
        self.assertEqual(data.get('username'), 'bob_test')

    def test_partner_joined_dm_event(self):
        client1 = self.socketio.test_client(self.app)
        client2 = self.socketio.test_client(self.app)

        server_app.sid_to_username[client1.sid] = "user1"
        server_app.sid_to_username[client2.sid] = "user2"

        # user1 joins DM
        client1.emit("join_dm", {"user1": "user1", "user2": "user2"})
        client1.get_received() # Clear events

        # user2 joins DM -> user1 should receive partner_joined_dm
        client2.emit("join_dm", {"user1": "user1", "user2": "user2"})
        received1 = client1.get_received()
        joined_events = [e for e in received1 if e["name"] == "partner_joined_dm"]
        self.assertEqual(len(joined_events), 1)
        self.assertEqual(joined_events[0]["args"][0]["user"], "user2")
