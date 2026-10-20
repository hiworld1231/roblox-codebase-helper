"""Derived from BloxySync (MIT); see third_party/BloxySync-LICENSE.

Conservative, incremental Luau AST index over a revisioned Instance snapshot.

This is a navigation aid, not a Luau type checker or a proof of runtime behavior.
Only tree-sitter syntax nodes are used to discover code relationships.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
from collections import defaultdict, deque
from copy import deepcopy
from typing import Any

from tree_sitter import Language, Node, Parser, Tree
import tree_sitter_luau

SCRIPT_CLASSES = {"Script", "LocalScript", "ModuleScript"}
DEPENDENCY_KINDS = {"require", "remote_fire", "remote_listen", "call", "datastore_open"}
from importlib.metadata import version
from pathlib import Path

ANALYZER_VERSION = ("context-luau-1/" + version("tree-sitter") + "/" + version("tree-sitter-luau")
                    + "/" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
PROFILES = {"minimal": (1200, 0), "balanced": (4000, 1), "deep": (10000, 3)}


def _hash(value: Any) -> str:
    data = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


def _walk(node: Node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


class GraphIndex:
    """Rebuild relationships against each snapshot; reparse only changed source.

    Public results are JSON-compatible copies. IDs in edges refer to ``nodes``;
    unresolved expressions have explicit nodes and confidence ``unresolved``.
    """

    def __init__(self, cache=None) -> None:
        self.cache = cache
        self.revision = 0
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.objects: dict[str, dict] = {}
        self._parser = Parser(Language(tree_sitter_luau.language()))
        self._trees: dict[str, tuple[str, Tree]] = {}
        self._analyses: dict[str, dict] = {}
        self._diagnostics: list[dict] = []
        self._history: dict[int, dict[str, str]] = {}
        self._children: dict[str | None, list[str]] = {}
        self._edge_ids: set[str] = set()
        self.stats: dict = {}

    def update(self, objects: list[dict], revision: int) -> dict:
        if not isinstance(revision, int) or revision < 0:
            raise ValueError("revision must be a nonnegative integer")
        indexed: dict[str, dict] = {}
        for obj in objects:
            if not isinstance(obj.get("id"), str) or not obj["id"]:
                raise ValueError("each object must have a nonempty string id")
            if obj["id"] in indexed:
                raise ValueError(f"duplicate object id: {obj['id']}")
            indexed[obj["id"]] = deepcopy(obj)
        previous = set(self.objects)
        self.objects = indexed
        self.revision = revision
        self.nodes, self.edges, self._diagnostics, self._edge_ids = {}, [], [], set()
        children: dict[str | None, list[str]] = defaultdict(list)
        for oid, obj in indexed.items():
            children[obj.get("parent")].append(oid)
        self._children = dict(children)
        for oid, obj in indexed.items():
            path = self._path(oid)
            self.nodes[oid] = {
                "id": oid, "kind": "script" if obj.get("className") in SCRIPT_CLASSES else "instance",
                "name": obj.get("name", oid), "className": obj.get("className", "Instance"),
                "objectId": oid, "path": path, "file": obj.get("filePath") or obj.get("file") or path,
                "source": "snapshot", "confidence": "snapshot", "line": 1,
                "sourceAvailable": isinstance(obj.get("source"), str),
            }
            if obj.get("parent") is not None and obj["parent"] not in indexed:
                self._diag(oid, None, "MISSING_PARENT", "Parent absent from this snapshot; path is incomplete.")
        self._index_metadata()
        # Code extraction depends on names/classes/parents, but not unrelated sources.
        topology_hash = _hash([(i, o.get("name"), o.get("className"), o.get("parent"),
                                o.get("filePath"), o.get("file")) for i, o in sorted(indexed.items())])
        parsed = reused = analyzed = reused_analysis = 0
        active = {}
        analyses = {}
        for oid, obj in sorted(indexed.items()):
            source = obj.get("source")
            if obj.get("className") not in SCRIPT_CLASSES:
                continue
            if not isinstance(source, str):
                self._diag(oid, None, "SOURCE_UNAVAILABLE", "Source was not supplied; code dependencies are unknown.")
                continue
            raw = source.encode("utf-8")
            digest = _hash(raw)
            self.nodes[oid]["contentHash"] = digest
            cache_key = _hash([ANALYZER_VERSION, oid, digest, topology_hash])
            analysis = self._analyses.get(oid) or (self.cache.analysis_get(cache_key) if self.cache else None)
            if analysis and analysis["sourceHash"] == digest and analysis["topologyHash"] == topology_hash:
                self.nodes.update(deepcopy(analysis["nodes"]))
                self.edges.extend(deepcopy(analysis["edges"]))
                self._edge_ids.update(e["id"] for e in analysis["edges"])
                self._diagnostics.extend(deepcopy(analysis["diagnostics"]))
                reused_analysis += 1
                if oid in self._trees:
                    active[oid] = self._trees[oid]
                    reused += 1
            else:
                cached = self._trees.get(oid)
                if cached and cached[0] == digest:
                    tree = cached[1]
                    reused += 1
                else:
                    tree = self._parser.parse(raw)
                    parsed += 1
                active[oid] = (digest, tree)
                before_nodes = set(self.nodes)
                before_edges = len(self.edges)
                before_diagnostics = len(self._diagnostics)
                self._analyze(oid, tree, raw)
                analysis = {"sourceHash": digest, "topologyHash": topology_hash,
                            "nodes": {i: deepcopy(self.nodes[i]) for i in
                                      (self.nodes.keys() - before_nodes) |
                                      {e["target"] for e in self.edges[before_edges:] if e["target"] not in indexed}},
                            "edges": deepcopy(self.edges[before_edges:]),
                            "diagnostics": deepcopy(self._diagnostics[before_diagnostics:])}
                analyzed += 1
                if self.cache:
                    self.cache.analysis_put(cache_key, analysis)
            analyses[oid] = analysis
        self._trees = active
        self._analyses = analyses
        self.edges.sort(key=lambda e: (e["objectId"], e["line"], e["kind"], e["target"]))
        self._history[revision] = {oid: _hash(obj) for oid, obj in indexed.items()}
        while len(self._history) > 32:
            del self._history[next(iter(self._history))]
        self.stats = {"revision": revision, "parsed": parsed, "reused": reused,
                      "analyzed": analyzed, "reusedAnalysis": reused_analysis,
                      "removed": len(previous - set(indexed)), "nodes": len(self.nodes),
                      "edges": len(self.edges), "diagnostics": len(self._diagnostics),
                      "parser": "tree-sitter-luau", "analysis": "conservative static AST"}
        return deepcopy(self.stats)

    def _index_metadata(self) -> None:
        def edge(oid, target, kind, detail=""):
            eid = _hash([oid, target, kind, detail])[:24]
            self._edge_ids.add(eid)
            self.edges.append({"id": eid, "source": oid, "target": target, "kind": kind,
                               "objectId": oid, "file": self.nodes[oid]["file"], "line": 1,
                               "column": 1, "confidence": "snapshot", "detail": detail,
                               "evidence": "Instance snapshot metadata; line is not a source location"})

        for oid, obj in sorted(self.objects.items()):
            if obj.get("parent") in self.objects:
                edge(obj["parent"], oid, "parent_child")
            for tag in obj.get("tags", []):
                if not isinstance(tag, str):
                    continue
                tid = "tag:" + tag
                self.nodes[tid] = {"id": tid, "name": tag, "kind": "tag", "confidence": "snapshot"}
                edge(oid, tid, "has_tag")
            for field, kind in (("attributes", "attribute"), ("properties", "property")):
                for key, value in obj.get(field, {}).items():
                    if key == "Source":
                        continue
                    pid = f"{kind}:{oid}:{key}"
                    self.nodes[pid] = {"id": pid, "name": key, "kind": kind, "value": deepcopy(value),
                                       "objectId": oid, "confidence": "snapshot"}
                    edge(oid, pid, "has_" + kind)
                    if isinstance(value, str) and value.startswith("rbxassetid://") and value[13:].isdigit():
                        aid = "asset:" + value[13:]
                        self.nodes[aid] = {"id": aid, "name": value, "kind": "asset", "confidence": "snapshot"}
                        edge(oid, aid, "uses_asset", key)

    def _path(self, oid: str) -> str:
        parts, seen = [], set()
        while oid in self.objects and oid not in seen:
            seen.add(oid)
            obj = self.objects[oid]
            parts.append(str(obj.get("name", oid)))
            oid = obj.get("parent")
        if oid in seen:
            parts.append("<parent-cycle>")
        elif oid is not None:
            parts.append("<missing-parent>")
        return ".".join(reversed(parts))

    def _diag(self, oid: str, node: Node | None, code: str, message: str) -> None:
        self._diagnostics.append({"objectId": oid, "file": self.nodes.get(oid, {}).get("file", oid),
                                  "line": node.start_point.row + 1 if node else 1,
                                  "code": code, "severity": "warning", "message": message})

    def _edge(self, oid: str, target: str, kind: str, node: Node, confidence="static", detail="") -> None:
        detail = detail[:320]
        line = node.start_point.row + 1
        identity = _hash([oid, target, kind, line, node.start_point.column, detail])[:24]
        if identity in self._edge_ids:
            return
        self._edge_ids.add(identity)
        self.edges.append({"id": identity, "source": oid, "target": target, "kind": kind,
                           "objectId": oid, "file": self.nodes[oid]["file"], "line": line,
                           "column": node.start_point.column + 1,
                           "confidence": confidence, "detail": detail})

    def _analyze(self, oid: str, tree: Tree, raw: bytes) -> None:
        for syntax in _walk(tree.root_node):
            if syntax.type == "ERROR" or syntax.is_missing:
                self._diag(oid, syntax, "PARSE_ERROR", "Luau parser found invalid or unsupported syntax; relationships may be incomplete.")
        def txt(n: Node | None) -> str:
            return raw[n.start_byte:n.end_byte].decode("utf-8") if n else ""

        def literal(n: Node | None) -> str | None:
            if n is None or n.type != "string":
                return None
            if any(c.type == "interpolation" for c in n.named_children):
                return None
            value = txt(n)
            if value.startswith(("'", '"')):
                try:
                    result = ast.literal_eval(value)
                    return result if isinstance(result, str) else None
                except (SyntaxError, ValueError):
                    return None
            # Long strings are syntax-validated by tree-sitter; their content is literal.
            contents = n.children_by_field_name("content")
            return "".join(txt(c) for c in contents) if contents else None

        def child(parent: str | None, name: str) -> str | None:
            matches = [i for i in self._children.get(parent, []) if self.objects[i].get("name") == name]
            return matches[0] if len(matches) == 1 else None

        def resolve(n: Node | None, env: dict[str, str | None]) -> str | None:
            if n is None:
                return None
            if n.type == "identifier":
                return env.get(txt(n))
            if n.type in {"parenthesized_expression", "cast_expression"}:
                return resolve(n.named_children[0], env) if n.named_children else None
            if n.type in {"dot_index_expression", "bracket_index_expression"}:
                base = resolve(n.child_by_field_name("table"), env)
                field = n.child_by_field_name("field")
                key = txt(field) if n.type == "dot_index_expression" else literal(field)
                if base is None or key is None:
                    return None
                if key == "Parent" and base in self.objects:
                    return self.objects[base].get("parent")
                if base == "@game":
                    roots = [i for i, o in self.objects.items() if o.get("name") == key and
                             (o.get("parent") is None or self.objects.get(o.get("parent"), {}).get("className") == "DataModel")]
                    return roots[0] if len(roots) == 1 else None
                return child(base, key)
            if n.type == "function_call":
                name = n.child_by_field_name("name")
                args_node = n.child_by_field_name("arguments")
                args = args_node.named_children if args_node else []
                if name and name.type == "identifier" and txt(name) == "require" and env.get("require") == "@require":
                    target = resolve(args[0], env) if args else None
                    return target if self.objects.get(target, {}).get("className") == "ModuleScript" else None
                if name and name.type == "method_index_expression":
                    method = txt(name.child_by_field_name("method"))
                    base = resolve(name.child_by_field_name("table"), env)
                    key = literal(args[0]) if args else None
                    if method == "GetService" and base == "@game" and key:
                        if key == "DataStoreService":
                            return "@DataStoreService"
                        matches = [i for i, o in self.objects.items() if o.get("className") == key and
                                   (o.get("parent") is None or self.objects.get(o.get("parent"), {}).get("className") == "DataModel")]
                        return matches[0] if len(matches) == 1 else None
                    if method in {"WaitForChild", "FindFirstChild"} and base in self.objects and key:
                        # Recursive searches can have multiple valid targets; do not guess.
                        if method == "FindFirstChild" and len(args) > 1 and txt(args[1]) != "false":
                            return None
                        return child(base, key)
            return None

        def unresolved(n: Node, kind: str, detail: str) -> str:
            uid = f"unresolved:{oid}:{n.start_point.row + 1}:{n.start_point.column + 1}:{kind}"
            self.nodes[uid] = {"id": uid, "kind": "unresolved", "name": detail[:160],
                               "objectId": oid, "file": self.nodes[oid]["file"],
                               "line": n.start_point.row + 1, "confidence": "unresolved"}
            return uid

        def symbol(n: Node, name: str, kind: str) -> str:
            sid = f"symbol:{oid}:{kind}:{name}:{n.start_point.row + 1}:{n.start_point.column + 1}"
            self.nodes[sid] = {"id": sid, "kind": kind, "name": name, "objectId": oid,
                               "file": self.nodes[oid]["file"], "path": self.nodes[oid]["path"] + "." + name,
                               "line": n.start_point.row + 1, "confidence": "static"}
            self._edge(oid, sid, "declares", n)
            return sid

        def annotations(nodes, env):
            for annotation in nodes:
                for item in _walk(annotation):
                    if item.type == "identifier" and env.get("@type:" + txt(item)):
                        self._edge(oid, env["@type:" + txt(item)], "type_reference", item)

        def visit(n: Node, env: dict[str, str | None]) -> None:
            if n.type == "variable_declaration":
                assignment = next((c for c in n.named_children if c.type == "assignment_statement"), None)
                if assignment:
                    names_node = assignment.named_children[0]
                    names = names_node.children_by_field_name("name")
                    annotations([c for c in names_node.named_children if c not in names], env)
                    values = assignment.named_children[1].named_children
                    resolved = [resolve(v, env) for v in values]
                    for value in values:
                        visit(value, env)
                    for i, name in enumerate(names):
                        if name.type == "identifier":
                            val = values[i] if i < len(values) else None
                            env[txt(name)] = symbol(val, txt(name), "function") if val and val.type == "function_definition" else (resolved[i] if i < len(resolved) else None)
                else:
                    for identifier in _walk(n):
                        if identifier.type == "identifier":
                            env[txt(identifier)] = None
                return
            if n.type == "assignment_statement" and len(n.named_children) >= 2:
                names, values = n.named_children[:2]
                resolved = [resolve(v, env) for v in values.named_children]
                for value in values.named_children:
                    visit(value, env)
                for i, name in enumerate(names.children_by_field_name("name")):
                    if name.type == "identifier":
                        env[txt(name)] = resolved[i] if i < len(resolved) else None
                    elif name.type == "dot_index_expression" and txt(name.child_by_field_name("field")) in {"OnServerInvoke", "OnClientInvoke"}:
                        receiver = name.child_by_field_name("table")
                        target = resolve(receiver, env)
                        confidence = "static"
                        if self.objects.get(target, {}).get("className") != "RemoteFunction":
                            target, confidence = unresolved(name, "remote_listen", txt(receiver)), "unresolved"
                            self._diag(oid, name, "UNRESOLVED_REMOTE", "RemoteFunction callback receiver cannot be resolved.")
                        self._edge(oid, target, "remote_listen", name, confidence, txt(name))
                return
            if n.type in {"function_declaration", "function_definition"}:
                name = n.child_by_field_name("name")
                if name:
                    sid = symbol(n, txt(name), "function")
                    if name.type == "identifier":
                        env[txt(name)] = sid
                nested = env.copy()
                params = n.child_by_field_name("parameters")
                if params:
                    for param in params.named_children:
                        ident = next((c for c in param.named_children if c.type == "identifier"), None)
                        if ident:
                            nested[txt(ident)] = None
                            annotations([c for c in param.named_children if c != ident], env)
                annotations([c for c in n.named_children if c not in [name, params, n.child_by_field_name("body")]], env)
                body = n.child_by_field_name("body")
                if body:
                    visit(body, nested)
                    invalidate_assignments(body, env)
                return
            if n.type == "type_definition":
                name = n.child_by_field_name("name")
                if name:
                    env["@type:" + txt(name)] = symbol(n, txt(name), "type")
                return
            if n.type == "for_statement":
                nested = env.copy()
                clause = n.child_by_field_name("clause")
                if clause:
                    if clause.type == "for_numeric_clause":
                        nested[txt(clause.child_by_field_name("name"))] = None
                    else:
                        variables = next((c for c in clause.named_children if c.type == "variable_list"), None)
                        if variables:
                            for variable in variables.children_by_field_name("name"):
                                nested[txt(variable)] = None
                    visit(clause, env.copy())
                body = n.child_by_field_name("body")
                if body:
                    visit(body, nested)
                invalidate_assignments(n, env)
                return
            if n.type == "function_call":
                name = n.child_by_field_name("name")
                args_node = n.child_by_field_name("arguments")
                args = args_node.named_children if args_node else []
                if name and name.type == "identifier" and txt(name) == "require" and env.get("require") == "@require":
                    target = resolve(args[0], env) if args else None
                    valid = self.objects.get(target, {}).get("className") == "ModuleScript"
                    if not valid:
                        target = unresolved(n, "require", txt(args[0]) if args else "require without argument")
                        self._diag(oid, n, "UNRESOLVED_REQUIRE", "Dynamic, external, ambiguous, or absent require target; runtime resolution is unverified.")
                    self._edge(oid, target, "require", n, "static" if valid else "unresolved", txt(n))
                elif name and name.type == "identifier" and (env.get(txt(name)) or "").startswith("symbol:"):
                    self._edge(oid, env[txt(name)], "call", n, detail=txt(n))
                if name and name.type in {"method_index_expression", "dot_index_expression"}:
                    method = txt(name.child_by_field_name("method") or name.child_by_field_name("field"))
                    receiver = name.child_by_field_name("table")
                    if method in {"GetDataStore", "GetOrderedDataStore"} and resolve(receiver, env) == "@DataStoreService":
                        store_name = literal(args[0]) if args else None
                        scope = literal(args[1]) if len(args) > 1 else "global"
                        if store_name is not None and scope is not None:
                            target = "datastore:" + _hash([method, store_name, scope])[:24]
                            self.nodes[target] = {"id": target, "kind": "datastore", "name": store_name,
                                                  "scope": scope, "ordered": method == "GetOrderedDataStore",
                                                  "confidence": "static", "runtimeVerified": False}
                            self._edge(oid, target, "datastore_open", n, "static", txt(n))
                        else:
                            target = unresolved(n, "datastore_open", txt(n))
                            self._edge(oid, target, "datastore_open", n, "unresolved", txt(n))
                            self._diag(oid, n, "UNRESOLVED_DATASTORE", "Dynamic DataStore name/scope; runtime access unverified.")
                    kind, target = None, None
                    if method in {"FireServer", "FireClient", "FireAllClients", "InvokeServer", "InvokeClient"}:
                        kind, target = "remote_fire", resolve(receiver, env)
                    elif method in {"Connect", "Once", "Wait"} and receiver and receiver.type == "dot_index_expression":
                        event = txt(receiver.child_by_field_name("field"))
                        if event in {"OnServerEvent", "OnClientEvent"}:
                            kind, target = "remote_listen", resolve(receiver.child_by_field_name("table"), env)
                    if kind:
                        if self.objects.get(target, {}).get("className") not in {"RemoteEvent", "UnreliableRemoteEvent", "RemoteFunction"}:
                            target = unresolved(n, kind, txt(receiver))
                            self._diag(oid, n, "UNRESOLVED_REMOTE", "Remote receiver cannot be resolved against the supplied snapshot.")
                            confidence = "unresolved"
                        else:
                            confidence = "static"
                        self._edge(oid, target, kind, n, confidence, txt(n))
            # Branch/loop environments are intentionally not merged into the outer scope.
            for c in n.named_children:
                visit(c, env.copy() if c.type == "block" else env)
                if c.type == "block":
                    invalidate_assignments(c, env)

        def invalidate_assignments(n, env):
            # A possible assignment in a branch/closure invalidates an outer alias.
            # This deliberately prefers an unresolved relationship to a false proof.
            for assignment in _walk(n):
                if assignment.type != "assignment_statement" or assignment.parent.type == "variable_declaration":
                    continue
                variables = assignment.named_children[0]
                for variable in variables.children_by_field_name("name"):
                    if variable.type == "identifier" and txt(variable) in env:
                        env[txt(variable)] = None

        visit(tree.root_node, {"game": "@game", "script": oid, "require": "@require"})

    def query(self, text: str = "", kind: str | None = None, limit: int = 50) -> list[dict]:
        if limit < 0:
            raise ValueError("limit must be nonnegative")
        needle = text.casefold()
        found = [n for n in self.nodes.values() if (kind is None or n["kind"] == kind) and
                 (not needle or needle in " ".join(str(n.get(k, "")) for k in ("id", "name", "path", "className")).casefold())]
        return deepcopy(sorted(found, key=lambda n: (n.get("path", ""), n["id"]))[:limit])

    def search(self, text: str = "", kind: str | None = None, limit: int = 50) -> list[dict]:
        return self.query(text, kind, limit)

    def dependencies(self, object_id: str, transitive: bool = False) -> list[dict]:
        pending, seen, result = deque([object_id]), set(), []
        while pending:
            oid = pending.popleft()
            if oid in seen:
                continue
            seen.add(oid)
            for edge in self.edges:
                if edge["source"] == oid and edge["kind"] in DEPENDENCY_KINDS:
                    result.append(edge)
                    if transitive and edge["confidence"] == "static":
                        pending.append(edge["target"])
        return deepcopy(result)

    def references(self, node_id: str) -> list[dict]:
        return deepcopy([e for e in self.edges if e["target"] == node_id and e["kind"] not in {"declares", "parent_child"}])

    def impact(self, node_id: str) -> list[dict]:
        pending, seen = deque([node_id]), {node_id}
        while pending:
            target = pending.popleft()
            for edge in self.edges:
                if edge["target"] == target and edge["kind"] in DEPENDENCY_KINDS and edge["confidence"] == "static":
                    if edge["source"] not in seen:
                        seen.add(edge["source"])
                        pending.append(edge["source"])
        seen.discard(node_id)
        return deepcopy([self.nodes[i] for i in sorted(seen) if i in self.nodes])

    def diagnostics(self, object_id: str | None = None) -> list[dict]:
        return deepcopy([d for d in self._diagnostics if object_id is None or d["objectId"] == object_id])

    def diff(self, from_revision: int) -> dict:
        if from_revision not in self._history:
            return {"fromRevision": from_revision, "revision": self.revision, "available": False,
                    "reason": "Revision is not in this process's 32-snapshot history."}
        before = self._history[from_revision]
        now = self._history[self.revision]
        return {"fromRevision": from_revision, "revision": self.revision, "available": True,
                "added": sorted(now.keys() - before.keys()), "removed": sorted(before.keys() - now.keys()),
                "changed": sorted(i for i in before.keys() & now.keys() if before[i] != now[i])}

    def context(self, ids: list[str] | str, profile: str = "balanced", budget_tokens: int | None = None) -> dict:
        if profile not in PROFILES:
            raise ValueError(f"profile must be one of {', '.join(PROFILES)}")
        default, depth = PROFILES[profile]
        budget = default if budget_tokens is None else budget_tokens
        if not isinstance(budget, int) or budget < 256:
            raise ValueError("budget_tokens must be an integer >= 256")
        requested = [ids] if isinstance(ids, str) else list(ids)
        chosen, queue = [], deque((i, 0) for i in requested)
        seen = set()
        while queue:
            node_id, distance = queue.popleft()
            if node_id in seen:
                continue
            seen.add(node_id)
            if node_id not in self.nodes:
                continue
            chosen.append(node_id)
            if distance < depth:
                for edge in self.dependencies(node_id):
                    if edge["confidence"] == "static":
                        queue.append((edge["target"], distance + 1))
        result = {"revision": self.revision, "profile": profile, "budgetTokens": budget,
                  "estimatedTokens": 0, "tokenEstimate": "ceil(UTF-8 JSON bytes/4); heuristic, not tokenizer",
                  "truncated": False, "text": ""}
        segments = [f"Revision {self.revision}. Static snapshot evidence; runtime behavior unverified.\n"]
        if any(i not in self.nodes for i in requested):
            segments.append("Unknown IDs: " + ", ".join(i for i in requested if i not in self.nodes) + "\n")
        for node_id in chosen:
            node = self.nodes[node_id]
            segments.append("NODE " + json.dumps(node, ensure_ascii=False, sort_keys=True) + "\n")
            for edge in self.dependencies(node_id):
                segments.append("EDGE " + json.dumps(edge, ensure_ascii=False, sort_keys=True) + "\n")
            for diag in self.diagnostics(node_id):
                segments.append("DIAGNOSTIC " + json.dumps(diag, ensure_ascii=False, sort_keys=True) + "\n")
            if node_id in self.objects and isinstance(self.objects[node_id].get("source"), str):
                source = self.objects[node_id]["source"]
                # Keep line labels so truncated excerpts remain auditable.
                segments.append("SOURCE " + node_id + "\n")
                segments.extend(f"{line}: {text}\n" for line, text in enumerate(source.splitlines(), 1))
        for segment in segments:
            candidate = dict(result, text=result["text"] + segment)
            if math.ceil(len(json.dumps(candidate, ensure_ascii=False).encode()) / 4) > budget - 8:
                result["truncated"] = True
                break
            result["text"] += segment
        # Include the envelope in the estimate, not only source characters.
        for _ in range(4):
            estimate = math.ceil(len(json.dumps(result, ensure_ascii=False).encode()) / 4)
            if result["estimatedTokens"] == estimate:
                break
            result["estimatedTokens"] = estimate
        return result
