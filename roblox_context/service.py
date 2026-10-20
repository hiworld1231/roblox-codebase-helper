"""Small, bounded queries over explicitly selected Studio sessions."""
from __future__ import annotations

import base64
from collections import deque
import json
import math
import threading

from ._graph_base import GraphIndex, DEPENDENCY_KINDS
from .navigation import export_navigation, paths
from .store import SCRIPTS, ContextError, atomic_text, digest, realm, require


def tokens(value):
    return math.ceil(len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()) / 4)


def node_output(node):
    return {k: node[k] for k in ("id", "kind", "name", "className", "path", "line", "confidence", "sourceAvailable", "scope", "ordered") if k in node and not (k == "line" and node.get("confidence") == "snapshot")}


def edge_output(edge):
    return {k: edge[k] for k in ("source", "target", "kind", "line", "confidence", "detail") if k in edge}


class Service:
    def __init__(self, store, bridge):
        self.store, self.bridge = store, bridge
        self.graphs, self.builds = {}, 0
        self.graph_lock = threading.RLock()

    def fence(self, sid, expected_revision=None):
        self.bridge.fence(sid)
        status = self.store.status(sid)
        require(status["fresh"], "stale", "Plugin state is not current")
        if expected_revision is not None:
            require(status["revision"] == expected_revision, "stale_revision", "Revision changed; search again before reading")
        return status

    def coverage(self, sid):
        objects = self.store.objects(sid)
        scripts = [i for i, o in objects.items() if o["className"] in SCRIPTS]
        with self.store.lock:
            versions = dict(self.store.db.execute("SELECT id,version FROM sources WHERE session=?", (sid,)))
        indexed = sum(versions.get(i) == objects[i].get("sourceVersion", 0) for i in scripts)
        return {"scripts": len(scripts), "indexedScripts": indexed,
                "completeStaticCoverage": indexed == len(scripts),
                "limits": "Only explicitly fetched sources are analyzed. Dynamic/runtime links remain unverified."}

    def envelope(self, sid):
        status = self.store.status(sid)
        return {"session": sid, "placeId": status["place"], "studioJobId": status["job"], "revision": status["revision"],
                "fresh": status["fresh"], "coverage": self.coverage(sid)}

    def overview(self, sid=None, resume=False, limit=20, cursor=None, budget=4000):
        if resume:
            from .selective import resume_task
            return resume_task(self, sid, limit, cursor, budget)
        if sid is None:
            sessions = self.store.sessions()
            return {"sessions": sessions[:10], "totalSessions": len(sessions), "truncated": len(sessions) > 10,
                    "selection": "Pass an explicit session ID to every project query", "allowedPlaceId": self.store.allowed_place}
        self.fence(sid)
        with self.store.lock:
            export_navigation(self.store, sid)
            return {**self.envelope(sid), "workspace": str(self.store.workspace(sid)),
                    "metrics": {**self.bridge.metrics, "graphBuilds": self.builds}, "sourceAuthority": "Studio edit-time source"}

    def graph(self, sid):
        with self.graph_lock, self.store.lock:
            revision = self.store.status(sid)["revision"]
            cached = self.graphs.get(sid)
            if cached and cached[0] == revision:
                return cached[1]
            graph = cached[1] if cached else GraphIndex(cache=self.store)
            objects = self.store.objects(sid)
            for oid, obj in objects.items():
                if obj["className"] in SCRIPTS:
                    source = self.store.source(sid, oid)
                    if source:
                        obj["source"] = source[1]
            graph.update(list(objects.values()), revision)
            self.graphs[sid] = (revision, graph)
            self.builds += 1
            return graph

    def analyze(self, sid, ids, depth=0):
        require(0 <= depth <= 3 and len(ids) <= 20, "scope", "Use depth 0..3 and at most 20 explicit roots")
        queue, seen = deque((i, 0) for i in ids), set()
        while queue:
            oid, level = queue.popleft()
            if oid in seen:
                continue
            require(len(seen) < 40, "scope", "Dependency read limit reached; request a smaller scope")
            seen.add(oid)
            obj = self.store.objects(sid).get(oid)
            if obj and obj["className"] in SCRIPTS:
                self.bridge.source(sid, oid)
            graph = self.graph(sid)
            if level < depth:
                queue.extend((e["target"], level + 1) for e in graph.dependencies(oid) if e["kind"] == "require" and e["confidence"] == "static")
        return self.graph(sid)

    def page(self, sid, rows, key, limit=20, cursor=None, budget=4000):
        require(1 <= limit <= 100 and 256 <= budget <= 24000, "bounds", "Limit 1..100; budget 256..24000")
        revision = self.store.status(sid)["revision"]
        offset = 0
        if cursor:
            try:
                value = json.loads(base64.urlsafe_b64decode(cursor))
            except Exception as error:
                raise ContextError("cursor", "Invalid cursor") from error
            require(value.get("key") == digest([sid, key]) and value.get("revision") == revision, "stale_cursor", "Cursor scope/revision changed; restart this query")
            offset = value.get("offset")
            require(type(offset) is int and 0 <= offset <= len(rows), "cursor", "Invalid cursor offset")
        result = {**self.envelope(sid), "items": [], "total": len(rows), "nextCursor": None,
                  "truncated": False, "estimatedTokens": 0, "tokenEstimate": "ceil(UTF-8 JSON bytes/4); heuristic"}
        for row in rows[offset:offset + limit]:
            candidate = {**result, "items": result["items"] + [row]}
            # Reserve space for cursor and final token count.
            if tokens(candidate) > budget - 150:
                break
            result["items"].append(row)
        end = offset + len(result["items"])
        if end < len(rows):
            result["truncated"] = True
            result["nextCursor"] = base64.urlsafe_b64encode(json.dumps({"revision": revision, "offset": end, "key": digest([sid, key])}).encode()).decode()
            if not result["items"]:
                result["omission"] = "Next item exceeds budget; increase budget_tokens"
        for _ in range(4):
            estimate = tokens(result)
            if result["estimatedTokens"] == estimate:
                break
            result["estimatedTokens"] = estimate
        require(result["estimatedTokens"] <= budget, "budget", "Envelope exceeds budget; increase budget_tokens")
        return result

    def search(self, sid, text, kind=None, limit=20, cursor=None, budget=4000, search_in="metadata", scope_id=None):
        require(search_in in ("metadata", "source"), "search_in", "Choose metadata or source")
        if search_in == "source":
            from .selective import source_search
            return source_search(self, sid, text, scope_id, kind, limit, cursor, budget)
        self.fence(sid)
        with self.graph_lock, self.store.lock:
            graph = self.graph(sid)
            rows = [node_output(n) for n in graph.search(text, kind, limit=100_000)]
            for row in rows:
                obj = graph.objects.get(row["id"])
                if obj:
                    row["filesystemPath"] = None
                    row["realm"], row["realmEvidence"] = realm(obj, row["path"])
            return self.page(sid, rows, ["search", text, kind], limit, cursor, budget)

    def query(self, sid, action, oid, analyze_ids=(), depth=1, limit=20, cursor=None, budget=4000):
        self.fence(sid)
        # Fetch selected roots only, never all potential callers automatically.
        self.analyze(sid, list(dict.fromkeys([oid, *analyze_ids])), depth if action == "dependencies" else 0)
        with self.graph_lock, self.store.lock:
            graph = self.graph(sid)
            require(oid in graph.nodes, "unknown_object", "Select an indexed object ID")
            if action == "dependencies":
                rows = [edge_output(e) for e in graph.dependencies(oid, transitive=depth > 1)]
            elif action == "references":
                rows = [edge_output(e) for e in graph.references(oid)]
            elif action == "impact":
                rows = [node_output(n) for n in graph.impact(oid)]
            elif action == "diagnostics":
                rows = graph.diagnostics(oid)
            else:
                raise ContextError("action", "Choose dependencies, references, impact or diagnostics")
            return self.page(sid, rows, ["graph", action, oid, sorted(analyze_ids), depth], limit, cursor, budget)

    def context(self, sid, ids, budget=4000, depth=1, include_source=False, cursor=None):
        self.fence(sid)
        graph = self.analyze(sid, ids, depth)
        with self.graph_lock, self.store.lock:
            graph = self.graph(sid)
            chosen, seen, queue = [], set(), deque((i, 0) for i in ids)
            while queue:
                oid, level = queue.popleft()
                if oid in seen:
                    continue
                require(oid in graph.nodes, "unknown_object", "Select an indexed object ID")
                seen.add(oid)
                chosen.append(oid)
                if level < depth:
                    queue.extend((e["target"], level + 1) for e in graph.dependencies(oid) if e["confidence"] == "static")
            rows = [{"node": node_output(graph.nodes[i]), "dependencies": [edge_output(e) for e in graph.dependencies(i)], "diagnostics": graph.diagnostics(i)} for i in chosen]
            # All metadata/dependency records precede optional source lines.
            if include_source:
                for oid in chosen:
                    if oid in graph.objects and isinstance(graph.objects[oid].get("source"), str):
                        rows.extend({"objectId": oid, "line": n, "text": line} for n, line in enumerate(graph.objects[oid]["source"].splitlines(), 1))
            return self.page(sid, rows, ["context", ids, depth, include_source], limit=100, cursor=cursor, budget=budget)

    def read(self, sid, oid, start, end, expected_revision=None, budget=4000, known_view=None):
        before = self.fence(sid, expected_revision)
        require(type(start) is int and type(end) is int and 1 <= start <= end and end - start < 500, "range", "Use 1-based inclusive ranges of at most 500 lines")
        sha, source = self.bridge.source(sid, oid)
        with self.store.lock:
            if expected_revision is not None:
                require(self.store.status(sid)["seq"] == before["seq"], "stale_revision", "Studio changed during the source read")
            require(self.store.status(sid)["fresh"], "stale", "Plugin state is not current")
            current = self.store.source(sid, oid)
            require(current is not None and current[0] == sha, "stale_source", "Source changed during read")
            lines = source.splitlines()
            require(start <= max(1, len(lines)), "range", "Start line exceeds source length")
            if known_view is not None:
                require(isinstance(known_view, dict) and all(k in known_view for k in ("session", "objectId", "sourceHash", "startLine", "endLine")), "known_view", "Use session, objectId, sourceHash, startLine and endLine from retained text")
                require(type(known_view["startLine"]) is int and type(known_view["endLine"]) is int and 1 <= known_view["startLine"] <= max(1, known_view["endLine"]), "known_view", "Invalid retained range")
                if (known_view["session"] == sid and known_view["objectId"] == oid and known_view["sourceHash"] == sha
                        and known_view["startLine"] <= start and known_view["endLine"] >= min(end, len(lines))):
                    result = {"session": sid, "objectId": oid, "sourceHash": sha, "revision": self.store.status(sid)["revision"],
                              "fresh": True, "startLine": start, "endLine": min(end, len(lines)), "unchanged": True}
                    require(tokens(result) <= budget, "budget", "Acknowledgement exceeds budget")
                    return result
            result = {**self.envelope(sid), "objectId": oid, "sourceHash": sha,
                      "startLine": start, "endLine": min(end, len(lines)), "totalLines": len(lines),
                      "lines": [{"line": i, "text": lines[i-1]} for i in range(start, min(end, len(lines)) + 1)],
                      "truncated": False}
            require(tokens(result) <= budget, "budget", "Range exceeds budget; request fewer lines or raise budget_tokens")
            return result

    def changed(self, sid, since, limit=20, cursor=None, budget=4000):
        self.fence(sid)
        with self.store.lock:
            return self.page(sid, self.store.changes(sid, since), ["changes", since], limit, cursor, budget)

    def checkpoint(self, sid, record=None):
        # Checkpoints remain usable offline, with explicit freshness in the envelope.
        self.store.status(sid)
        with self.store.lock:
            if record is not None:
                require(isinstance(record, dict) and tokens(record) <= 2000, "checkpoint", "Keep checkpoint under approximately 2000 tokens")
                fields = {"task", "decisions", "changedFiles", "checks", "issues", "nextSteps"}
                require(set(record) <= fields and isinstance(record.get("task"), str), "checkpoint", "Use task, decisions, changedFiles, checks, issues and nextSteps")
                require(all(isinstance(v, str) and len(v) <= 4000 if k == "task" else isinstance(v, list) and all(isinstance(i, str) for i in v) for k, v in record.items()), "checkpoint", "Use text task and arrays of text")
                data = {**record, "verifiedRevision": self.store.status(sid)["revision"]}
                with self.store.db:
                    self.store.db.execute("INSERT OR REPLACE INTO checkpoints VALUES(?,?)", (sid, json.dumps(data)))
                headings = {"decisions": "Decisions", "changedFiles": "Changed files", "checks": "Checks", "issues": "Open issues", "nextSteps": "Next steps"}
                lines = ["# Current task", "", record["task"], "", f"Recorded revision: {data['verifiedRevision']}. This is a checkpoint, not live test evidence."]
                for key, heading in headings.items():
                    lines += ["", "## " + heading, ""] + ["- " + i for i in record.get(key, [])]
                atomic_text(self.store.workspace(sid) / "docs/CURRENT_TASK.md", "\n".join(lines) + "\n")
            row = self.store.db.execute("SELECT data FROM checkpoints WHERE session=?", (sid,)).fetchone()
            return {**self.envelope(sid), "checkpoint": json.loads(row[0]) if row else None}
