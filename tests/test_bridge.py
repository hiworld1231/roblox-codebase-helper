"""Real loopback protocol, atomic snapshots and plugin command roundtrips."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from roblox_context.bridge import Bridge
from roblox_context.store import Store, ContextError
from test_context import SID, PLACE, metadata


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name), PLACE)
        self.bridge = Bridge(self.store, "local-test-token", 0)
        self.bridge.start()
        self.url = "http://127.0.0.1:" + str(self.bridge.http.server_port)

    def tearDown(self):
        self.bridge.close()
        self.store.close()
        self.temp.cleanup()

    def post(self, route, payload, token="local-test-token"):
        req = urllib.request.Request(self.url + route, data=json.dumps(payload).encode(), headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.load(response)

    def hello(self):
        self.post("/hello", {"session": SID, "placeId": PLACE, "jobId": "job", "name": "Untitled"})
        self.post("/snapshot/begin", {"session": SID, "seq": 0})
        self.post("/snapshot/chunk", {"session": SID, "items": metadata()})
        self.post("/snapshot/end", {"session": SID, "count": 6})

    def test_authentication_and_wrong_place_rejected_before_storage(self):
        for token, place in [("wrong", PLACE), ("local-test-token", 83440863421402)]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post("/hello", {"session": SID, "placeId": place, "jobId": "job", "name": "test"}, token)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
        self.assertEqual(self.store.sessions(), [])

    def test_partial_snapshot_cannot_publish_or_remove_objects(self):
        self.hello()
        self.post("/snapshot/begin", {"session": SID, "seq": 0})
        self.post("/snapshot/chunk", {"session": SID, "items": metadata()[:2]})
        self.assertFalse(self.store.status(SID)["fresh"])
        self.assertEqual(len(self.store.objects(SID)), 6)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("/snapshot/end", {"session": SID, "count": 6})
        error.exception.close()
        self.assertEqual(len(self.store.objects(SID)), 6)
        self.assertFalse(self.store.status(SID)["fresh"])

    def test_source_roundtrip_is_direct_and_only_on_request(self):
        self.hello()
        self.assertEqual(self.bridge.metrics["sourceReads"], 0)
        results = []
        worker = threading.Thread(target=lambda: results.append(self.bridge.source(SID, "main")))
        worker.start()
        deadline = time.monotonic() + 3
        commands = []
        while not commands and time.monotonic() < deadline:
            commands = self.post("/poll", {"session": SID, "seq": 0})["commands"]
        self.assertEqual(len(commands), 1)
        command = commands[0]
        self.assertEqual(command["kind"], "source")
        self.assertNotIn("source", command)
        self.post("/result", {"session": SID, "seq": 0, "requestId": command["requestId"], "version": 0, "source": "return 'private source'"})
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0][1], "return 'private source'")
        self.bridge.source(SID, "main")
        self.assertEqual(self.bridge.metrics["sourceReads"], 1)
        revision = self.store.status(SID)["revision"]
        for _ in range(3):
            self.assertEqual(self.post("/poll", {"session": SID, "seq": 0})["commands"], [])
        self.assertEqual(self.store.status(SID)["revision"], revision)
        self.assertEqual(self.bridge.metrics["metadataBatches"], 1)

    def test_sequence_gap_requests_resnapshot_and_pause_is_stale(self):
        self.hello()
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("/delta", {"session": SID, "seq": 2, "upserts": [], "removed": []})
        error.exception.close()
        self.assertTrue(self.post("/poll", {"session": SID, "seq": 2})["resync"])
        with self.assertRaises(ContextError):
            self.bridge.fence(SID)

    def test_competing_launch_does_not_invalidate_live_state(self):
        self.hello()
        another = Store(Path(self.temp.name), PLACE, reset_live=False)
        try:
            with self.assertRaises(OSError):
                Bridge(another, "local-test-token", self.bridge.http.server_port)
            self.assertTrue(self.store.status(SID)["fresh"])
        finally:
            another.close()


if __name__ == "__main__":
    unittest.main()
