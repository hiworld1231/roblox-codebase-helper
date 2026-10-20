"""Authenticated loopback intake and on-demand plugin requests in the MCP process."""
from __future__ import annotations

from collections import deque
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import socket
import secrets
import threading
import time

from .store import ContextError, require


class Bridge:
    def __init__(self, store, token, port=38491):
        self.store, self.token = store, token
        self.lock = threading.Condition(threading.RLock())
        self.pending, self.jobs, self.staging = {}, {}, {}
        self.metrics = {"sourceReads": 0, "sourceBytes": 0, "fences": 0, "metadataBatches": 0}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    require(hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + outer.token), "authentication", "Local authentication required")
                    size = int(self.headers.get("Content-Length", "0"))
                    # JSON escaping can expand a bounded 2 MB UTF-8 source body.
                    require(0 < size <= 12_100_000, "body_size", "Invalid request size")
                    payload = json.loads(self.rfile.read(size))
                    require(isinstance(payload, dict), "request", "JSON object required")
                    result = outer.dispatch(self.path, payload)
                    self.send_response(200)
                except (ContextError, ValueError, KeyError, TypeError) as error:
                    result = {"error": {"code": getattr(error, "code", "request"), "message": str(error)}}
                    self.send_response(403 if getattr(error, "code", "") in {"authentication", "wrong_place"} else 400)
                except Exception:
                    result = {"error": {"code": "internal", "message": "Bridge request failed"}}
                    self.send_response(500)
                raw = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        class LocalHTTPServer(ThreadingHTTPServer):
            # Windows SO_REUSEADDR can permit two owners on the same listening port.
            allow_reuse_address = os.name != "nt"
            def server_bind(self):
                if os.name == "nt":
                    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                super().server_bind()
        self.http = LocalHTTPServer(("127.0.0.1", port), Handler)
        self.http.daemon_threads = True
        self.thread = threading.Thread(target=self.http.serve_forever, name="context-loopback", daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)

    def dispatch(self, path, p):
        if path == "/client/health":
            return {"protocol": 1, "root": str(self.store.root.resolve())}
        if path == "/client/tool":
            from .runtime import METHODS
            require(p.get("method") in METHODS and isinstance(p.get("args"), list), "request", "Unknown client method")
            require(hasattr(self, "service"), "busy", "Bridge starting; retry")
            return getattr(self.service, p["method"])(*p["args"])
        sid = p.get("session")
        if path == "/hello":
            status = self.store.hello(sid, p["placeId"], p["jobId"], p["name"])
            return {"resync": not status["ready"], "seq": status["seq"]}
        self.store.status(sid)
        if path == "/ui/status":
            objects = self.store.objects(sid)
            from .store import SCRIPTS
            scripts = [i for i, o in objects.items() if o["className"] in SCRIPTS]
            with self.store.lock:
                versions = dict(self.store.db.execute("SELECT id,version FROM sources WHERE session=?", (sid,)))
            return {"scripts": len(scripts), "cachedScripts": sum(versions.get(i) == objects[i].get("sourceVersion", 0) for i in scripts),
                    "revision": self.store.status(sid)["revision"], "workspace": str(self.store.workspace(sid)), "saved": True}
        if path == "/ui/backup":
            require(self.store.status(sid)["fresh"], "stale", "Refresh metadata before backing up")
            import sqlite3
            from pathlib import Path
            directory = self.store.private / "backups"
            directory.mkdir(mode=0o700, exist_ok=True)
            directory.chmod(0o700)
            target = directory / (time.strftime("context-%Y%m%d-%H%M%S-") + secrets.token_hex(4) + ".sqlite3")
            target.touch(mode=0o600)
            try:
                backup = sqlite3.connect(target)
                try:
                    with self.store.lock:
                        self.store.db.backup(backup)
                finally:
                    backup.close()
                return {"saved": True, "path": str(target), "bytes": target.stat().st_size,
                        "includesCachedCode": True}
            except Exception:
                target.unlink(missing_ok=True)
                raise
        if path == "/pause":
            self.store.mark_stale(sid)
            return {"ok": True}
        if path == "/snapshot/begin":
            require(type(p["seq"]) is int and p["seq"] >= self.store.status(sid)["seq"], "sequence", "Invalid snapshot sequence")
            with self.lock:
                self.staging[sid] = {"seq": p["seq"], "items": [], "started": time.monotonic()}
            self.store.mark_stale(sid)
            return {"ok": True}
        if path == "/snapshot/chunk":
            with self.lock:
                stage = self.staging.get(sid)
                require(stage is not None and time.monotonic() - stage["started"] < 120, "snapshot", "Snapshot expired")
                require(isinstance(p["items"], list) and len(p["items"]) <= 500, "snapshot", "Chunk limit is 500 objects")
                stage["items"].extend(p["items"])
                require(len(stage["items"]) <= 100_000, "snapshot", "Metadata scope too large")
            return {"ok": True}
        if path == "/snapshot/end":
            with self.lock:
                stage = self.staging.pop(sid, None)
            require(stage is not None and time.monotonic() - stage["started"] < 120 and len(stage["items"]) == p["count"], "snapshot", "Incomplete or expired snapshot")
            self.store.ingest(sid, stage["seq"], stage["items"], snapshot=True)
            from .navigation import export_navigation
            export_navigation(self.store, sid)
            self.metrics["metadataBatches"] += 1
            return {"ok": True}
        if path == "/delta":
            self.store.ingest(sid, p["seq"], p["upserts"], p.get("removed", []))
            from .navigation import export_navigation
            export_navigation(self.store, sid)
            self.metrics["metadataBatches"] += 1
            return {"ok": True}
        if path == "/poll":
            self.store.touch(sid)
            status = self.store.status(sid)
            if not status["ready"] or p.get("seq") != status["seq"]:
                self.store.mark_stale(sid)
                return {"resync": True, "commands": []}
            with self.lock:
                commands = list(self.pending.pop(sid, deque()))
                commands = [c for c in commands if c["requestId"] in self.jobs]
            return {"resync": False, "commands": commands}
        if path == "/result":
            with self.lock:
                job = self.jobs.get(p.get("requestId"))
                require(job is not None and job["session"] == sid, "request", "Unknown or expired command")
                require(p.get("seq") == self.store.status(sid)["seq"], "stale_source", "Plugin revision did not match acknowledged metadata")
                if "error" in p:
                    job["result"] = {"error": {"code": "plugin", "message": str(p["error"])[:300]}}
                elif job["kind"] == "source":
                    require(p.get("version") == job["version"], "stale_source", "Source version changed")
                    self.store.put_source(sid, job["id"], p["version"], p["source"])
                    self.metrics["sourceReads"] += 1
                    self.metrics["sourceBytes"] += len(p["source"].encode())
                    job["result"] = {"ok": True}
                else:
                    self.metrics["fences"] += 1
                    job["result"] = {"ok": True}
                self.lock.notify_all()
            return {"ok": True}
        raise ContextError("route", "Unknown bridge route")

    def request(self, sid, kind, timeout=12, **fields):
        require(self.store.status(sid)["fresh"], "disconnected", "Plugin unavailable or metadata incomplete; reconnect before using context")
        request_id = secrets.token_hex(12)
        command = {"requestId": request_id, "kind": kind, **fields}
        with self.lock:
            require(len(self.jobs) < 64, "busy", "Too many pending requests")
            self.jobs[request_id] = {"session": sid, **command}
            self.pending.setdefault(sid, deque()).append(command)
            deadline = time.monotonic() + timeout
            try:
                while "result" not in self.jobs[request_id]:
                    remaining = deadline - time.monotonic()
                    require(remaining > 0, "timeout", "Studio did not acknowledge the request; context freshness unverified")
                    self.lock.wait(min(remaining, 1))
                result = self.jobs[request_id]["result"]
                if "error" in result:
                    raise ContextError(result["error"]["code"], result["error"]["message"])
                return result
            finally:
                self.jobs.pop(request_id, None)

    def fence(self, sid):
        return self.request(sid, "fence")

    def source(self, sid, oid):
        cached = self.store.source(sid, oid)
        if cached:
            return cached
        obj = self.store.objects(sid)[oid]
        self.request(sid, "source", id=oid, version=obj.get("sourceVersion", 0))
        cached = self.store.source(sid, oid)
        require(cached is not None, "stale_source", "Script changed during source retrieval")
        return cached
