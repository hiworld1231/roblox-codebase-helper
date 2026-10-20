"""Private revisioned metadata, selective source and analysis cache."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time

SCRIPTS = {"Script", "LocalScript", "ModuleScript"}


class ContextError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def require(condition, code, message):
    if not condition:
        raise ContextError(code, message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic_text(path: Path, text: str, private=False):
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    fd, temporary = tempfile.mkstemp(prefix=".context-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporary, 0o600 if private else 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def realm(obj, path):
    context = obj.get("runContext", "Legacy")
    if obj["className"] == "LocalScript" or context == "Client":
        return "client", "Script class or explicit RunContext; execution also depends on placement/enabled state"
    if obj["className"] == "Script" and context == "Server":
        return "server", "Explicit RunContext; execution also depends on enabled state"
    if obj["className"] == "Script":
        return "server (inferred)", "Legacy Script; placement/runtime activation unverified"
    if obj["className"] == "ModuleScript":
        if ".ServerScriptService." in path or ".ServerStorage." in path:
            return "server (inferred)", "Server-only container; callers not necessarily indexed"
        return "unknown / shared candidate", "ModuleScript executes in its caller's realm; callers may be unindexed"
    return "n/a", "Metadata object"


class Store:
    def __init__(self, root: Path, allowed_place: int, reset_live=True):
        self.root = Path(root).resolve()
        self.private = self.root / ".context"
        self.private.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.private.chmod(0o700)
        self.lock = threading.RLock()
        self.allowed_place = allowed_place
        self.db = sqlite3.connect(self.private / "context.sqlite3", check_same_thread=False)
        (self.private / "context.sqlite3").chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY, place INTEGER, job TEXT, name TEXT,
          seq INTEGER DEFAULT 0, revision INTEGER DEFAULT 0,
          ready INTEGER DEFAULT 0, heartbeat REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS objects (
          session TEXT, id TEXT, data TEXT, PRIMARY KEY(session,id));
        CREATE TABLE IF NOT EXISTS sources (
          session TEXT, id TEXT, version INTEGER, hash TEXT, PRIMARY KEY(session,id));
        CREATE TABLE IF NOT EXISTS blobs (hash TEXT PRIMARY KEY, source TEXT);
        CREATE TABLE IF NOT EXISTS analyses (key TEXT PRIMARY KEY, data TEXT);
        CREATE TABLE IF NOT EXISTS changes (
          session TEXT, revision INTEGER, data TEXT, PRIMARY KEY(session,revision));
        CREATE TABLE IF NOT EXISTS checkpoints (session TEXT PRIMARY KEY, data TEXT);
        """)
        # A persisted heartbeat is never evidence of a live connection after restart.
        if reset_live:
            with self.db:
                self.db.execute("UPDATE sessions SET ready=0,heartbeat=0")

    def close(self):
        with self.lock:
            self.db.close()

    def hello(self, sid, place, job, name):
        require(isinstance(sid, str) and 8 <= len(sid) <= 100 and all(c.isalnum() or c in "-_" for c in sid), "identity", "Invalid session ID")
        require(type(place) is int and place >= 0 and (self.allowed_place is None or place == self.allowed_place), "wrong_place", "This bridge is restricted to the configured place")
        require(isinstance(job, str) and len(job) <= 100 and isinstance(name, str) and len(name) <= 300, "identity", "Invalid Studio identity")
        with self.lock, self.db:
            previous = self.db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
            if previous:
                require(previous["place"] == place and previous["job"] == job, "identity", "Session identity changed")
            else:
                self.db.execute("INSERT INTO sessions(id,place,job,name) VALUES(?,?,?,?)", (sid, place, job, name))
            self.db.execute("UPDATE sessions SET heartbeat=? WHERE id=?", (time.time(), sid))
        return self.status(sid)

    def status(self, sid):
        with self.lock:
            row = self.db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
            require(row is not None, "unknown_session", "Choose a connected plugin session")
            result = dict(row)
            result["connected"] = time.time() - result.pop("heartbeat") < 8
            result["fresh"] = bool(result["ready"] and result["connected"])
            result["ready"] = bool(result["ready"])
            return result

    def sessions(self):
        with self.lock:
            return [self.status(r[0]) for r in self.db.execute("SELECT id FROM sessions ORDER BY heartbeat DESC,id")]

    def touch(self, sid):
        with self.lock, self.db:
            self.status(sid)
            self.db.execute("UPDATE sessions SET heartbeat=? WHERE id=?", (time.time(), sid))

    def mark_stale(self, sid):
        with self.lock, self.db:
            self.db.execute("UPDATE sessions SET ready=0 WHERE id=?", (sid,))

    @staticmethod
    def validate(obj):
        require(isinstance(obj, dict), "metadata", "Object must be a record")
        require(isinstance(obj.get("id"), str) and 0 < len(obj["id"]) <= 100, "metadata", "Invalid object ID")
        require(isinstance(obj.get("name"), str) and len(obj["name"]) <= 1000, "metadata", "Invalid name")
        require(isinstance(obj.get("className"), str) and len(obj["className"]) <= 100, "metadata", "Invalid class")
        require(obj.get("parent") is None or isinstance(obj["parent"], str), "metadata", "Invalid parent")
        require(type(obj.get("sourceVersion", 0)) is int and obj.get("sourceVersion", 0) >= 0, "metadata", "Invalid source version")
        require(obj.get("runContext", "Legacy") in ("Legacy", "Server", "Client", "Plugin"), "metadata", "Invalid RunContext")
        require(type(obj.get("disabled", False)) is bool, "metadata", "Invalid disabled state")
        return {k: obj[k] for k in ("id", "name", "className", "parent", "runContext", "disabled", "sourceVersion") if k in obj}

    def objects(self, sid):
        # This query deliberately does not touch source blobs.
        with self.lock:
            return {r[0]: json.loads(r[1]) for r in self.db.execute("SELECT id,data FROM objects WHERE session=?", (sid,))}

    @staticmethod
    def topology_valid(objects):
        done = set()
        for oid in objects:
            trail, current = set(), oid
            while current is not None and current not in done:
                require(current in objects, "metadata", "Incomplete parent chain")
                require(current not in trail, "metadata", "Parent cycle")
                trail.add(current)
                current = objects[current].get("parent")
            done.update(trail)

    def _record(self, sid, data):
        self.db.execute("UPDATE sessions SET revision=revision+1 WHERE id=?", (sid,))
        revision = self.db.execute("SELECT revision FROM sessions WHERE id=?", (sid,)).fetchone()[0]
        self.db.execute("INSERT INTO changes VALUES(?,?,?)", (sid, revision, json.dumps(data)))
        return revision

    def ingest(self, sid, seq, upserts, removed=(), snapshot=False):
        require(type(seq) is int and seq >= 0, "sequence", "Invalid sequence")
        require(isinstance(upserts, list) and isinstance(removed, (list, tuple)), "metadata", "Invalid delta")
        cleaned = [self.validate(o) for o in upserts]
        require(len({o["id"] for o in cleaned}) == len(cleaned), "metadata", "Duplicate IDs")
        require(all(isinstance(i, str) for i in removed), "metadata", "Invalid removal IDs")
        with self.lock:
            status = self.status(sid)
            if not snapshot and (not status["ready"] or seq != status["seq"] + 1):
                self.mark_stale(sid)
                raise ContextError("sequence_gap", "Complete metadata resnapshot required")
            require(not snapshot or seq >= status["seq"], "sequence", "Old snapshot rejected")
            old = self.objects(sid)
            new = {} if snapshot else dict(old)
            new.update({o["id"]: o for o in cleaned})
            for oid in removed:
                new.pop(oid, None)
            self.topology_valid(new)
            # Paths are metadata, including descendants affected by a parent move.
            from .navigation import paths
            before_paths, after_paths = paths(old), paths(new)
            change = {"added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()),
                      "changed": sorted(i for i in new.keys() & old.keys() if new[i] != old[i] or before_paths[i] != after_paths[i])}
            details = {i: {"beforePath": before_paths.get(i), "currentPath": after_paths.get(i)}
                       for key in ("added", "removed", "changed") for i in change[key]}
            with self.db:
                if snapshot:
                    self.db.execute("DELETE FROM objects WHERE session=?", (sid,))
                self.db.executemany("INSERT OR REPLACE INTO objects VALUES(?,?,?)", [(sid, o["id"], json.dumps(o)) for o in cleaned])
                self.db.executemany("DELETE FROM objects WHERE session=? AND id=?", [(sid, i) for i in removed])
                for oid in old.keys() - new.keys():
                    self.db.execute("DELETE FROM sources WHERE session=? AND id=?", (sid, oid))
                if any(change.values()):
                    self._record(sid, {**change, "paths": details})
                self.db.execute("UPDATE sessions SET seq=?,ready=1,heartbeat=? WHERE id=?", (seq, time.time(), sid))
            return self.status(sid)

    def source(self, sid, oid):
        with self.lock:
            metadata = self.db.execute("SELECT data FROM objects WHERE session=? AND id=?", (sid, oid)).fetchone()
            obj = json.loads(metadata[0]) if metadata else None
            require(obj is not None and obj["className"] in SCRIPTS, "not_script", "Select a script ID")
            row = self.db.execute("SELECT s.version,s.hash,b.source FROM sources s JOIN blobs b ON b.hash=s.hash WHERE s.session=? AND s.id=?", (sid, oid)).fetchone()
            return (row["hash"], row["source"]) if row and row["version"] == obj.get("sourceVersion", 0) else None

    def put_source(self, sid, oid, version, source):
        require(isinstance(source, str) and len(source.encode()) <= 2_000_000, "source_size", "Source unavailable or larger than 2 MB")
        with self.lock:
            obj = self.objects(sid).get(oid)
            require(obj is not None and obj["className"] in SCRIPTS and obj.get("sourceVersion", 0) == version, "stale_source", "Script changed while reading; retry")
            sha = hashlib.sha256(source.encode()).hexdigest()
            existing = self.source(sid, oid)
            with self.db:
                self.db.execute("INSERT OR IGNORE INTO blobs VALUES(?,?)", (sha, source))
                self.db.execute("INSERT OR REPLACE INTO sources VALUES(?,?,?,?)", (sid, oid, version, sha))
                if not existing or existing[0] != sha:
                    self._record(sid, {"indexed": [oid]})
            return sha

    def changes(self, sid, since, include_paths=False):
        status = self.status(sid)
        require(type(since) is int and 0 <= since <= status["revision"], "revision", "Invalid starting revision")
        with self.lock:
            rows = [{"revision": r[0], **json.loads(r[1])} for r in self.db.execute("SELECT revision,data FROM changes WHERE session=? AND revision>? ORDER BY revision", (sid, since))]
            if not include_paths:
                for row in rows:
                    row.pop("paths", None)
            return rows

    def analysis_get(self, key):
        with self.lock:
            row = self.db.execute("SELECT data FROM analyses WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def analysis_put(self, key, data):
        with self.lock, self.db:
            self.db.execute("INSERT OR IGNORE INTO analyses VALUES(?,?)", (key, json.dumps(data)))

    def workspace(self, sid):
        self.status(sid)
        return self.root / "projects" / str(self.status(sid)["place"]) / sid
