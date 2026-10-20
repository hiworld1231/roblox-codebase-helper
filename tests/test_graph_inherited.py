# Adapted from BloxySync (MIT); see third_party/BloxySync-LICENSE.
"""AST evidence, incremental invalidation and bounded context contract."""
import json
import math
import unittest
from copy import deepcopy

from roblox_context._graph_base import GraphIndex


def fixture(source):
    return [
        {"id": "rs", "name": "ReplicatedStorage", "className": "ReplicatedStorage", "parent": None},
        {"id": "mods", "name": "Modules", "className": "Folder", "parent": "rs"},
        {"id": "mod", "name": "Config", "className": "ModuleScript", "parent": "mods", "source": "return {value = 1}"},
        {"id": "remote", "name": "Action", "className": "RemoteEvent", "parent": "rs"},
        {"id": "function", "name": "Fetch", "className": "RemoteFunction", "parent": "rs"},
        {"id": "main", "name": "Main", "className": "Script", "parent": "rs", "source": source},
    ]


class GraphTests(unittest.TestCase):
    def graph(self, source):
        graph = GraphIndex()
        graph.update(fixture(source), 1)
        return graph

    def test_real_luau_ast_require_function_type_and_line_evidence(self):
        graph = self.graph('''-- require(script.NoSuchModule) is only a comment
local RS = game:GetService("ReplicatedStorage")
local config = require(RS:WaitForChild("Modules"):FindFirstChild("Config"))
export type State = {value: number}
local state: State = {value = 1}
local function work(value: State): State return value end
work(state)
''')
        deps = graph.dependencies("main")
        requires = [e for e in deps if e["kind"] == "require"]
        self.assertEqual([(e["target"], e["line"]) for e in requires], [("mod", 3)])
        self.assertEqual(requires[0]["file"], "ReplicatedStorage.Main")
        self.assertEqual(requires[0]["confidence"], "static")
        self.assertEqual(len(graph.query(kind="function")), 1)
        types = graph.query("State", kind="type")
        self.assertEqual(len(types), 1)
        self.assertEqual(len(graph.references(types[0]["id"])), 3)
        self.assertTrue(any(e["kind"] == "call" for e in deps))
        self.assertEqual(graph.diagnostics(), [])

    def test_parent_brackets_cast_alias_and_shadowed_require(self):
        graph = self.graph('''local target = (script.Parent["Modules"].Config :: ModuleScript)
local conf = require(target)
local function f(require) require(script.Parent.Modules.Config) end
local require = function(x) return x end
require(script.Parent.Modules.Config)
''')
        requires = [e for e in graph.dependencies("main") if e["kind"] == "require"]
        self.assertEqual(len(requires), 1)
        self.assertEqual(requires[0]["target"], "mod")

    def test_dynamic_require_and_remote_are_explicitly_uncertain(self):
        graph = self.graph('local n = "Config"\nrequire(script.Parent.Modules[n])\nx:FireServer()\nrequire(123)')
        self.assertEqual(len(graph.dependencies("main")), 3)
        self.assertTrue(all(e["confidence"] == "unresolved" for e in graph.dependencies("main")))
        self.assertEqual(len(graph.diagnostics("main")), 3)
        self.assertEqual(graph.impact("mod"), [])

    def test_remote_listens_fires_and_function_callbacks(self):
        graph = self.graph('''local R = game:GetService("ReplicatedStorage")
R.Action.OnServerEvent:Connect(function(player) print(player) end)
R.Action:FireAllClients("x")
R.Fetch.OnServerInvoke = function(player) return true end
R.Fetch:InvokeClient(nil)
''')
        self.assertEqual([(e["target"], e["kind"]) for e in graph.dependencies("main")],
                         [("remote", "remote_listen"), ("remote", "remote_fire"),
                          ("function", "remote_listen"), ("function", "remote_fire")])
        self.assertEqual([n["id"] for n in graph.impact("remote")], ["main"])
        self.assertEqual(len(graph.references("function")), 2)

    def test_parse_cache_metadata_and_topology_changes(self):
        objects = fixture('require(script.Parent.Modules.Config)')
        graph = GraphIndex()
        first = graph.update(objects, 1)
        edge_id = graph.dependencies("main")[0]["id"]
        self.assertEqual(first["parsed"], 2)
        second = graph.update(objects, 2)
        self.assertEqual((second["parsed"], second["reused"]), (0, 2))
        self.assertEqual(graph.dependencies("main")[0]["id"], edge_id)
        changed = deepcopy(objects)
        next(o for o in changed if o["id"] == "mod")["name"] = "Renamed"
        third = graph.update(changed, 3)
        self.assertEqual(third["parsed"], 0)
        self.assertEqual(graph.dependencies("main")[0]["confidence"], "unresolved")
        self.assertEqual(graph.diff(2)["changed"], ["mod"])
        changed[-1]["source"] = 'require(script.Parent.Modules.Renamed)'
        self.assertEqual(graph.update(changed, 4)["parsed"], 1)
        self.assertEqual(graph.dependencies("main")[0]["target"], "mod")

    def test_delete_add_and_rename_snapshot_diff(self):
        objects = fixture('require(script.Parent.Modules.Config)')
        graph = GraphIndex()
        graph.update(objects, 1)
        changed = [o for o in objects if o["id"] != "mod"]
        changed.append({"id": "new", "name": "Config", "className": "ModuleScript", "parent": "mods", "source": "return 2"})
        result = graph.update(changed, 2)
        self.assertEqual(result["removed"], 1)
        self.assertEqual(graph.diff(1)["removed"], ["mod"])
        self.assertEqual(graph.diff(1)["added"], ["new"])
        self.assertEqual(graph.dependencies("main")[0]["target"], "new")
        self.assertNotIn("mod", graph._trees)

    def test_reverse_transitive_impact_and_cycle(self):
        objects = fixture('require(script.Parent.Modules.Config)')
        next(o for o in objects if o["id"] == "mod")["source"] = 'require(script.Parent.Other)'
        objects.append({"id": "other", "name": "Other", "className": "ModuleScript", "parent": "mods", "source": 'require(script.Parent.Config)'})
        graph = GraphIndex()
        graph.update(objects, 1)
        self.assertEqual({n["id"] for n in graph.impact("other")}, {"main", "mod"})
        self.assertEqual(len(graph.dependencies("main", transitive=True)), 3)

    def test_reassignment_branches_parameters_and_loop_bindings_do_not_create_false_edges(self):
        graph = self.graph('''local R = game:GetService("ReplicatedStorage")
if condition then R = unknown end
require(R.Modules.Config)
local R = game:GetService("ReplicatedStorage")
for R in pairs(list) do require(R.Modules.Config) end
local function f(R) require(R.Modules.Config) end
''')
        requires = [e for e in graph.dependencies("main") if e["kind"] == "require"]
        self.assertEqual(len(requires), 3)
        self.assertTrue(all(e["confidence"] == "unresolved" for e in requires))

    def test_duplicate_child_names_are_not_guessed(self):
        objects = fixture('require(script.Parent.Modules.Config)')
        objects.append({"id": "duplicate", "name": "Config", "className": "ModuleScript", "parent": "mods", "source": "return 2"})
        graph = GraphIndex()
        graph.update(objects, 1)
        self.assertEqual(graph.dependencies("main")[0]["confidence"], "unresolved")

    def test_no_sources_and_invalid_syntax_are_diagnostic(self):
        objects = fixture('local x = function(')
        del objects[2]["source"]
        graph = GraphIndex()
        graph.update(objects, 1)
        codes = {d["code"] for d in graph.diagnostics()}
        self.assertIn("SOURCE_UNAVAILABLE", codes)
        self.assertIn("PARSE_ERROR", codes)

    def test_context_budget_includes_json_and_utf8_and_is_deterministic(self):
        graph = self.graph('local x = "Rocket 🚀"\n' * 1000)
        for profile in ("minimal", "balanced", "deep"):
            result = graph.context(["main"], profile, 256)
            actual = math.ceil(len(json.dumps(result, ensure_ascii=False).encode()) / 4)
            self.assertLessEqual(actual, 256)
            self.assertEqual(result["estimatedTokens"], actual)
            self.assertTrue(result["truncated"])
            self.assertEqual(result, graph.context("main", profile, 256))
        with self.assertRaises(ValueError):
            graph.context("main", budget_tokens=10)
        self.assertIn("Unknown IDs: absent", graph.context("absent")["text"])

    def test_snapshots_are_copied_and_queries_do_not_mutate_index(self):
        objects = fixture('return 1')
        graph = GraphIndex()
        graph.update(objects, 1)
        objects[-1]["source"] = "changed"
        node = graph.query("Main")[0]
        node["name"] = "changed"
        self.assertEqual(graph.nodes["main"]["name"], "Main")
        self.assertEqual(graph.objects["main"]["source"], "return 1")

    def test_duplicate_id_validation_and_bounded_revision_history(self):
        graph = GraphIndex()
        with self.assertRaises(ValueError):
            graph.update([{"id": "x"}, {"id": "x"}], 1)
        for revision in range(35):
            graph.update([], revision)
        self.assertFalse(graph.diff(0)["available"])
        self.assertTrue(graph.diff(34)["available"])

    def test_long_string_paths_and_recursive_find_are_conservative(self):
        graph = self.graph('local R = game:GetService([[ReplicatedStorage]])\nrequire(R.Modules:WaitForChild([[Config]]))\nrequire(R:FindFirstChild("Config", true))')
        dependencies = graph.dependencies("main")
        self.assertEqual(dependencies[0]["target"], "mod")
        self.assertEqual(dependencies[1]["confidence"], "unresolved")


if __name__ == "__main__":
    unittest.main()
