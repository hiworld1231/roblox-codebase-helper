#!/usr/bin/env python3
"""Measure compact request + response JSON for identical local fixture tasks; no model calls."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from roblox_context.store import Store
from roblox_context.service import Service
from roblox_context.mcp_server import create_server


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def measurement(calls, answer):
    return {"calls": len(calls), "requestBytes": sum(size(q) for q, r in calls),
            "responseBytes": sum(size(r) for q, r in calls), "answer": answer}


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-schema', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/improvements-benchmark.json')
    args = parser.parse_args()
    sid = 'benchmark-session'; place = 73706828303910
    with tempfile.TemporaryDirectory() as temporary:
        store = Store(Path(temporary), place)
        try:
            store.hello(sid, place, 'fixture-job', 'Fixture')
            objects = [{"id": "root", "name": "game", "className": "DataModel"},
                       {"id": "scope", "name": "Systems", "className": "Folder", "parent": "root"}]
            bodies = {
                'inventory': 'local Inventory = {}\nfunction Inventory.add(items, name)\n    items[name] = (items[name] or 0) + 1\nend\nreturn Inventory',
                'movement': 'local Movement = {}\nfunction Movement.step(position, velocity, dt)\n    return position + velocity * dt\nend\nreturn Movement',
                'network': 'local Network = {}\nfunction Network.send(remote, payload)\n    remote:FireServer(payload)\nend\nreturn Network',
            }
            objects += [{"id": i, "name": i.title(), "className": "ModuleScript", "parent": "scope", "sourceVersion": 0} for i in bodies]
            store.ingest(sid, 0, objects, snapshot=True)
            class CachedPlugin:
                metrics = {'sourceReads': 0}
                def fence(self, session):
                    assert store.status(session)['fresh']
                def source(self, session, oid):
                    if not store.source(session, oid):
                        store.put_source(session, oid, 0, bodies[oid]); self.metrics['sourceReads'] += 1
                    return store.source(session, oid)
            service = Service(store, CachedPlugin())
            def call(name, kwargs, method, *pos, **kw):
                return ({'name': name, 'arguments': {'session_id': sid, **kwargs}}, method(sid, *pos, **kw))
            baseline = []
            baseline.append(call('project_search', {'text':'Systems'}, service.search, 'Systems'))
            for oid in sorted(bodies):
                baseline.append(call('read_source', {'object_id':oid,'start_line':1,'end_line':5}, service.read, oid, 1, 5))
            selected = [call('project_search', {'text':'FireServer','scope_id':'scope','search_in':'source'}, service.search, 'FireServer', search_in='source', scope_id='scope')]
            original = service.read(sid, 'network', 1, 5)
            known = {k: original[k] for k in ('session','objectId','sourceHash','startLine','endLine')}
            repeated = [call('read_source', {'object_id':'network','start_line':1,'end_line':5}, service.read, 'network', 1, 5)]
            conditional = [call('read_source', {'object_id':'network','start_line':1,'end_line':5,'known_view':known}, service.read, 'network', 1, 5, known_view=known)]
            service.checkpoint(sid, {'task':'Investigate network transport','checks':['Recorded fixture inspection'],'nextSteps':['Review selected caller']})
            checkpoint_revision = store.status(sid)['revision']
            store.ingest(sid, 1, [{**objects[-1], 'name': 'Transport'}])
            separate = [call('project_overview', {}, service.overview), call('task_checkpoint', {}, service.checkpoint),
                        call('changed_context', {'since_revision':checkpoint_revision}, service.changed, checkpoint_revision)]
            resumed = [call('project_overview', {'resume':True}, service.overview, resume=True)]
            schemas = [t.model_dump(mode='json',exclude_none=True) for t in asyncio.run(create_server(service).list_tools())]
            old = json.loads(args.baseline_schema.read_text()) if args.baseline_schema else None
            data = {'method':'Compact UTF-8 JSON name/arguments + parsed result payload; excludes JSON-RPC framing. Local deterministic fixture, not account quota.',
                    'schemaBytes': {'before':size(old) if old else None,'after':size(schemas)},
                    'tasks': {'find_literal': {'baseline':measurement(baseline, {'network':[3]}),'improved':measurement(selected, {'network':[3]}),'complete':selected[0][1]['complete']},
                              'retained_read': {'baseline':measurement(repeated, 'lines 1..5'),'improved':measurement(conditional, 'same retained lines 1..5'),'unchanged':conditional[0][1]['unchanged']},
                              'resume': {'baseline':measurement(separate, 'checkpoint + network change'),'improved':measurement(resumed, 'checkpoint + network change'),'changedObjects':resumed[0][1]['total']}},
                    'limits':['Small code/range tasks can have little or negative savings.','Scope discovery costs both workflows; a large metadata listing is avoidable with focused queries.', 'Server-private source traffic and schema cost are distinct from model-visible response size.','Known text must still be retained by the caller; a hash alone is insufficient.']}
            if old: data['schemaBytes']['increase'] = size(schemas)-size(old)
            args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(data,ensure_ascii=False))
        finally:
            store.close()


if __name__ == '__main__':
    run()
