"""Correctness boundaries for selective, persistent Studio navigation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from roblox_context._graph_base import GraphIndex
from roblox_context.navigation import export_navigation
from roblox_context.service import Service, tokens
from roblox_context.store import Store, ContextError

SID = "test-session-one"
PLACE = 73706828303910


def metadata():
    return [
        {"id": "root", "name": "game", "className": "DataModel"},
        {"id": "rs", "name": "ReplicatedStorage", "className": "ReplicatedStorage", "parent": "root"},
        {"id": "ss", "name": "ServerScriptService", "className": "ServerScriptService", "parent": "root"},
        {"id": "mod", "name": "Config", "className": "ModuleScript", "parent": "rs", "sourceVersion": 0},
        {"id": "remote", "name": "Action", "className": "RemoteEvent", "parent": "rs"},
        {"id": "main", "name": "Main", "className": "Script", "parent": "ss", "sourceVersion": 0, "runContext": "Server", "disabled": True},
    ]


class FakePlugin:
    def __init__(self, store):
        self.store = store
        self.metrics = {"sourceReads": 0}
        self.text = {"mod": "return {value = 1}", "main": 'local R = game:GetService("ReplicatedStorage")\nlocal c = require(R.Config)\nR.Action:FireAllClients(c.value)\n-- PRIVATE-BODY\n'}

    def fence(self, sid):
        if not self.store.status(sid)["fresh"]:
            raise ContextError("disconnected", "Test plugin is offline")

    def source(self, sid, oid):
        cached = self.store.source(sid, oid)
        if not cached:
            obj = self.store.objects(sid)[oid]
            self.store.put_source(sid, oid, obj.get("sourceVersion", 0), self.text[oid])
            self.metrics["sourceReads"] += 1
        return self.store.source(sid, oid)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root, PLACE)
        self.store.hello(SID, PLACE, "job-one", "Untitled Game")
        self.store.ingest(SID, 0, metadata(), snapshot=True)
        self.plugin = FakePlugin(self.store)
        self.service = Service(self.store, self.plugin)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_metadata_search_and_export_never_read_source(self):
        with patch.object(self.plugin, "source", side_effect=AssertionError("Unexpected source read")):
            found = self.service.search(SID, "Config")
            export_navigation(self.store, SID)
        self.assertEqual(found["items"][0]["filesystemPath"], None)
        self.assertEqual(found["coverage"]["indexedScripts"], 0)
        self.assertNotIn("PRIVATE-BODY", json.dumps(found))
        text = (self.store.workspace(SID) / "docs/SCRIPT_INDEX.md").read_text()
        self.assertIn("Studio-only", text)
        self.assertTrue(export_navigation(self.store, SID, check=True))

    def test_on_demand_dependency_and_source_cache_idle(self):
        first = self.service.context(SID, ["main"])
        self.assertEqual(self.plugin.metrics["sourceReads"], 2)
        self.assertNotIn("PRIVATE-BODY", json.dumps(first))
        self.assertTrue(any(e["target"] == "mod" for e in first["items"][0]["dependencies"]))
        builds = self.service.builds
        self.service.context(SID, ["main"])
        self.service.search(SID, "Config")
        self.assertEqual(self.plugin.metrics["sourceReads"], 2)
        self.assertEqual(self.service.builds, builds)

    def test_reverse_links_expose_partial_coverage(self):
        empty = self.service.query(SID, "impact", "mod")
        self.assertEqual(empty["items"], [])
        self.assertFalse(empty["coverage"]["completeStaticCoverage"])
        found = self.service.query(SID, "impact", "mod", ["main"])
        self.assertEqual(found["items"][0]["id"], "main")

    def test_add_rename_move_delete_and_stale_index(self):
        export_navigation(self.store, SID)
        new = {"id": "second", "name": "Added", "className": "LocalScript", "parent": "rs", "sourceVersion": 0}
        self.store.ingest(SID, 1, [new])
        self.assertFalse(export_navigation(self.store, SID, check=True))
        new.update(name="Renamed", parent="ss")
        self.store.ingest(SID, 2, [new])
        self.assertEqual(self.service.search(SID, "Renamed")["items"][0]["path"], "game.ServerScriptService.Renamed")
        self.store.ingest(SID, 3, [], ["second"])
        changes = self.store.changes(SID, 1)
        self.assertTrue(any("second" in c.get("removed", []) for c in changes))

    def test_sequence_gap_and_incomplete_snapshot_fail_closed(self):
        with self.assertRaisesRegex(ContextError, "resnapshot"):
            self.store.ingest(SID, 2, [])
        self.assertFalse(self.store.status(SID)["fresh"])
        self.assertEqual(len(self.store.objects(SID)), 6)
        with self.assertRaises(ContextError):
            self.store.ingest(SID, 3, [{"id": "bad", "name": "Bad", "className": "Script", "parent": "missing"}], snapshot=True)
        self.assertFalse(self.store.status(SID)["fresh"])
        self.store.ingest(SID, 3, metadata(), snapshot=True)
        self.assertTrue(self.store.status(SID)["fresh"])

    def test_wrong_place_and_cross_session_isolation(self):
        with self.assertRaises(ContextError):
            self.store.hello("foreign-session", 83440863421402, "other", "CSS")
        other = "test-session-two"
        self.store.hello(other, PLACE, "job-two", "Other Untitled")
        self.store.ingest(other, 0, metadata()[:3], snapshot=True)
        self.plugin.source(SID, "main")
        self.assertEqual(self.service.search(other, "Main")["items"], [])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM sources WHERE session=?", (other,)).fetchone()[0], 0)
        with self.assertRaises(ContextError):
            self.store.hello(SID, PLACE, "wrong-job", "Untitled")

    def test_dirty_version_invalidates_source_and_revision_guard(self):
        previous = self.service.read(SID, "main", 2, 3)
        self.assertEqual([r["line"] for r in previous["lines"]], [2, 3])
        obj = self.store.objects(SID)["main"]
        obj["sourceVersion"] = 1
        self.store.ingest(SID, 1, [obj])
        self.assertIsNone(self.store.source(SID, "main"))
        with self.assertRaises(ContextError):
            self.store.put_source(SID, "main", 0, "old")
        with self.assertRaises(ContextError):
            self.service.read(SID, "main", 1, 1, previous["revision"])

    def test_ranges_budget_and_no_silent_line_truncation(self):
        for start, end in [(0, 1), (3, 2), (1, 501), (99, 100)]:
            with self.assertRaises(ContextError):
                self.service.read(SID, "main", start, end)
        self.assertEqual(self.service.read(SID, "main", 1, 500)["endLine"], 4)
        self.plugin.text["mod"] = "--" + "x" * 5000
        with self.assertRaises(ContextError):
            self.service.read(SID, "mod", 1, 1, budget=256)

    def test_pagination_and_cursor_revision(self):
        first = self.service.search(SID, "", limit=1)
        self.assertIsNotNone(first["nextCursor"])
        second = self.service.search(SID, "", limit=1, cursor=first["nextCursor"])
        self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])
        self.assertLessEqual(tokens(second), 4000)
        obj = self.store.objects(SID)["mod"]
        obj["name"] = "New"
        self.store.ingest(SID, 1, [obj])
        with self.assertRaises(ContextError):
            self.service.search(SID, "", limit=1, cursor=first["nextCursor"])

    def test_persistent_parse_cache_after_restart(self):
        self.service.context(SID, ["main"])
        revision = self.store.status(SID)["revision"]
        self.store.close()
        self.store = Store(self.root, PLACE)
        self.assertFalse(self.store.status(SID)["fresh"])
        self.store.hello(SID, PLACE, "job-one", "Untitled Game")
        self.store.ingest(SID, 0, metadata(), snapshot=True)
        self.assertEqual(self.store.status(SID)["revision"], revision)
        service = Service(self.store, FakePlugin(self.store))
        graph = service.graph(SID)
        self.assertEqual(graph.stats["parsed"], 0)
        self.assertEqual(graph.stats["reusedAnalysis"], 2)

    def test_duplicate_names_dynamic_require_invalid_luau_and_cycles(self):
        objects = metadata()
        objects += [{"id": "duplicate", "name": "Config", "className": "ModuleScript", "parent": "rs"}]
        objects[-2]["source"] = 'require(game.ReplicatedStorage.Config)\nrequire(foo)\nlocal ='
        graph = GraphIndex()
        graph.update(objects, 1)
        self.assertTrue(any(d["code"] == "PARSE_ERROR" for d in graph.diagnostics()))
        self.assertTrue(all(e["confidence"] == "unresolved" for e in graph.dependencies("main")))

    def test_datastore_names_scopes_and_dynamic_uncertainty(self):
        objects = metadata()
        objects[-1]["source"] = '''local ds = game:GetService("DataStoreService")
ds:GetDataStore("Profiles", "v1")
ds:GetOrderedDataStore("Wins")
ds:GetDataStore(dynamicName)
local ds = unknown
ds:GetDataStore("NotProven")'''
        graph = GraphIndex()
        graph.update(objects, 1)
        self.assertEqual({n["name"] for n in graph.nodes.values() if n["kind"] == "datastore"}, {"Profiles", "Wins"})
        self.assertEqual(len([d for d in graph.diagnostics() if d["code"] == "UNRESOLVED_DATASTORE"]), 1)

    def test_checkpoint_survives_offline_and_preserves_agent_rules(self):
        workspace = self.store.workspace(SID)
        workspace.mkdir(parents=True)
        (workspace / "AGENTS.md").write_text("# Existing\nKeep my rule.\n")
        export_navigation(self.store, SID)
        self.assertIn("Keep my rule.", (workspace / "AGENTS.md").read_text())
        self.service.checkpoint(SID, {"task": "Fix remote", "decisions": ["Verify caller"], "checks": ["Static only"]})
        self.store.mark_stale(SID)
        checkpoint = self.service.checkpoint(SID)
        self.assertFalse(checkpoint["fresh"])
        self.assertEqual(checkpoint["checkpoint"]["task"], "Fix remote")
        with self.assertRaises(ContextError):
            self.service.checkpoint(SID, {"task": "bad", "checks": "not a list"})


if __name__ == "__main__":
    unittest.main()
