"""Scoped literal retrieval and metadata-only task continuation."""
from __future__ import annotations

import base64
import json

from .navigation import paths
from .store import ContextError, SCRIPTS, digest, require


def encode_cursor(key, **position):
    return base64.urlsafe_b64encode(json.dumps({"key": digest(key), **position}, separators=(",", ":")).encode()).decode()


def decode_cursor(cursor, key):
    if not cursor:
        return {}
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor))
        require(isinstance(value, dict) and value.get("key") == digest(key), "stale_cursor", "Query, session or Studio state changed; restart")
        return value
    except (ValueError, TypeError, UnicodeError) as error:
        raise ContextError("cursor", "Invalid cursor") from error


def bounds(limit, budget):
    require(type(limit) is int and 1 <= limit <= 100 and 256 <= budget <= 24000, "bounds", "Limit 1..100; budget 256..24000")


def finish(result, budget):
    from .service import tokens
    result["estimatedTokens"] = 0
    result["tokenEstimate"] = "ceil(UTF-8 JSON bytes/4); heuristic"
    for _ in range(4):
        result["estimatedTokens"] = tokens(result)
    require(tokens(result) <= budget, "budget", "Response exceeds budget; increase budget_tokens")
    return result


def source_search(service, sid, text, scope, kind, limit, cursor, budget):
    from .service import tokens
    bounds(limit, budget)
    require(isinstance(text, str) and 0 < len(text) <= 1000 and "\n" not in text and "\r" not in text,
            "text", "Use a nonempty literal single-line query of at most 1000 characters")
    require(isinstance(scope, str) and scope, "scope", "Source search requires an explicit scope_id")
    require(kind is None or kind in SCRIPTS, "kind", "Source kind must be Script, LocalScript or ModuleScript")
    before = service.fence(sid)
    with service.store.lock:
        objects = service.store.objects(sid)
        require(scope in objects, "scope", "Unknown scope ID")
        explorer = paths(objects)
        selected = set([scope])
        children = {}
        for oid, obj in objects.items():
            children.setdefault(obj.get("parent"), []).append(oid)
        queue = [scope]
        while queue:
            for oid in children.get(queue.pop(), []):
                selected.add(oid)
                queue.append(oid)
        ids = sorted((i for i in selected if objects[i]["className"] in SCRIPTS
                      and (kind is None or objects[i]["className"] == kind)), key=lambda i: (explorer[i], i))
    key = ["source", sid, before["seq"], scope, text, kind]
    position = decode_cursor(cursor, key)
    index, line_offset = position.get("index", 0), position.get("line", 0)
    require(type(index) is int and 0 <= index <= len(ids) and type(line_offset) is int and line_offset >= 0,
            "cursor", "Invalid source position")
    result = {**service.envelope(sid), "searchIn": "source", "scopeId": scope, "studioSequence": before["seq"],
              "items": [], "unavailableSources": [], "checkedScripts": 0, "completedScripts": index,
              "remainingScripts": len(ids) - index, "totalScripts": len(ids), "nextCursor": None,
              "complete": False, "evidence": "Literal text hits only; not proof of dependency or execution"}
    count = 0
    needle = text.casefold()
    while index < len(ids) and result["checkedScripts"] < 20 and count < limit:
        oid = ids[index]
        result["checkedScripts"] += 1
        try:
            sha, source = service.bridge.source(sid, oid)
        except ContextError as error:
            # Freshness/transport failures abort: they cannot masquerade as missing source.
            if error.code not in ("plugin", "source_size"):
                raise
            unavailable = {"objectId": oid, "path": explorer[oid], "code": error.code}
            if tokens({**result, "unavailableSources": result["unavailableSources"] + [unavailable]}) > budget - 250:
                require(index > position.get("index", 0), "budget", "Unavailable-source record exceeds budget; increase budget_tokens")
                break
            result["unavailableSources"].append(unavailable)
            index, line_offset = index + 1, 0
            continue
        lines = source.splitlines()
        require(line_offset <= len(lines), "cursor", "Invalid source line position")
        group = {"objectId": oid, "path": explorer[oid], "sourceHash": sha, "matches": []}
        stopped = False
        for n in range(line_offset, len(lines)):
            folded = lines[n].casefold()
            if needle not in folded:
                continue
            # Bounded windows contain the match even on very long lines. Query is literal.
            hit = folded.find(needle)
            # Case folding may expand Unicode. Map back to original character position.
            original_hit, folded_offset = 0, 0
            for original_hit, character in enumerate(lines[n]):
                if folded_offset + len(character.casefold()) > hit:
                    break
                folded_offset += len(character.casefold())
            start = max(0, original_hit - 40)
            snippet = lines[n][start:start + 180]
            match = {"line": n + 1, "snippet": snippet, "column": original_hit + 1,
                     "snippetStartColumn": start + 1, "snippetTruncated": start > 0 or start + len(snippet) < len(lines[n])}
            candidate_group = {**group, "matches": group["matches"] + [match]}
            rows = result["items"][:-1] + [candidate_group] if group["matches"] else result["items"] + [candidate_group]
            if tokens({**result, "items": rows}) > budget - 250:
                require(count > 0 or index > position.get("index", 0), "budget", "Next match exceeds budget; increase budget_tokens")
                line_offset, stopped = n, True
                break
            group = candidate_group
            result["items"] = rows
            count += 1
            if count >= limit and n + 1 < len(lines):
                line_offset, stopped = n + 1, True
                break
        if stopped:
            break
        index, line_offset = index + 1, 0
    # One final Studio fence detects edits made during a multi-script search.
    after = service.fence(sid)
    require(after["seq"] == before["seq"], "stale_cursor", "Studio changed during search; restart")
    with service.store.lock:
        require(service.store.status(sid)["seq"] == before["seq"], "stale_cursor", "Studio changed during search; restart")
        result.update(revision=service.store.status(sid)["revision"], completedScripts=index,
                      remainingScripts=len(ids) - index, complete=index == len(ids))
        result["coverage"] = service.coverage(sid)
        result["matchLines"] = count
        if index < len(ids):
            result["nextCursor"] = encode_cursor(key, index=index, line=line_offset)
        result["absenceConfirmed"] = result["complete"] and not cursor and not result["items"] and not result["unavailableSources"]
        return finish(result, budget)


def resume_task(service, sid, limit, cursor, budget):
    from .service import tokens
    bounds(limit, budget)
    require(sid is not None, "session", "Resume requires an explicit session_id")
    status = service.store.status(sid)
    failure = None
    try:
        service.fence(sid)
    except ContextError as error:
        if error.code not in ("disconnected", "stale", "timeout", "sequence_gap"):
            raise
        failure = error.code
    with service.store.lock:
        status = service.store.status(sid)
        row = service.store.db.execute("SELECT data FROM checkpoints WHERE session=?", (sid,)).fetchone()
        checkpoint = json.loads(row[0]) if row else None
        key = ["resume", sid, status["revision"], status["seq"], digest(checkpoint)]
        position = decode_cursor(cursor, key)
        offset = position.get("offset", 0)
        require(type(offset) is int and offset >= 0, "cursor", "Invalid resume position")
        result = {**service.envelope(sid), "workspace": str(service.store.workspace(sid)),
                  "studioSequence": status["seq"], "connected": status["connected"],
                  "checkpointStatus": "recorded" if checkpoint else "missing",
                  "checksStatus": "Recorded by caller; not automatically rerun or verified",
                  "changesStatus": "unavailable" if failure else "available" if checkpoint else "no_checkpoint",
                  "items": [], "total": 0, "nextCursor": None, "truncated": False}
        if not cursor:
            result["checkpoint"] = checkpoint
        if failure:
            result.update(fresh=False, reason=failure)
            return finish(result, budget)
        if checkpoint is None:
            return finish(result, budget)
        rows = {}
        indexed = set()
        for event in service.store.changes(sid, checkpoint["verifiedRevision"], include_paths=True):
            indexed.update(event.get("indexed", []))
            for action in ("added", "changed", "removed"):
                for oid in event.get(action, []):
                    evidence = event.get("paths", {}).get(oid)
                    item = rows.get(oid)
                    if item is None:
                        item = {"objectId": oid, "firstChange": action, "lastChange": action,
                                "beforePath": evidence.get("beforePath") if evidence else None,
                                "currentPath": None, "pathsConfirmed": evidence is not None, "events": 0}
                        rows[oid] = item
                    item.update(lastChange=action, currentPath=evidence.get("currentPath") if evidence else None,
                                pathsConfirmed=item["pathsConfirmed"] and evidence is not None, events=item["events"] + 1)
        values = sorted(rows.values(), key=lambda r: r["objectId"])
        require(offset <= len(values), "cursor", "Invalid resume offset")
        result.update(total=len(values), indexedObjects=len(indexed), checkpointRevision=checkpoint["verifiedRevision"])
        for item in values[offset:offset + limit]:
            if tokens({**result, "items": result["items"] + [item]}) > budget - 150:
                break
            result["items"].append(item)
        end = offset + len(result["items"])
        if end < len(values):
            require(result["items"], "budget", "Checkpoint/next change exceeds budget; increase budget_tokens")
            result.update(truncated=True, nextCursor=encode_cursor(key, offset=end))
        return finish(result, budget)
