"""One bridge/database owner shared by Codex and Claude stdio clients; no daemon."""
from __future__ import annotations

import errno
import json
import threading
import urllib.error
import urllib.request

from .store import ContextError, Store

METHODS = frozenset(('overview', 'search', 'query', 'context', 'read', 'changed', 'checkpoint'))


class Runtime:
    def __init__(self, root, settings):
        self.root, self.settings = root.resolve(), settings
        self.bridge = self.store = self.service = None
        self.lock = threading.RLock()
        self._connect()

    def _remote(self, path, data):
        request = urllib.request.Request(f"http://127.0.0.1:{self.settings['port']}{path}",
            data=json.dumps(data).encode(), headers={'Authorization': 'Bearer ' + self.settings['token'], 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=3 if path == '/client/health' else 180) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            try:
                result = json.load(error)
            except (ValueError, OSError):
                raise ContextError('bridge_conflict', 'Port belongs to an incompatible bridge or profile; check installation') from error
            finally:
                error.close()
        if 'error' in result:
            raise ContextError(result['error']['code'], result['error']['message'])
        return result

    def _connect(self):
        from .bridge import Bridge
        from .service import Service
        with self.lock:
            if self.bridge:
                return
            store = Store(self.root, self.settings['placeId'], reset_live=False)
            try:
                bridge = Bridge(store, self.settings['token'], self.settings['port'])
            except OSError as error:
                store.close()
                if error.errno not in (errno.EADDRINUSE, errno.EACCES):
                    raise
                health = self._remote('/client/health', {})
                if health.get('root') != str(self.root) or health.get('protocol') != 1:
                    raise ContextError('bridge_conflict', 'Existing bridge uses another installation')
                return
            self.store, self.bridge = store, bridge
            self.service = Service(store, bridge)
            bridge.service = self.service
            with store.lock, store.db:
                store.db.execute('UPDATE sessions SET ready=0,heartbeat=0')
            bridge.start()

    def __getattr__(self, name):
        if name not in METHODS:
            raise AttributeError(name)
        def invoke(*args):
            if self.service:
                return getattr(self.service, name)(*args)
            try:
                return self._remote('/client/tool', {'method': name, 'args': list(args)})
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                # A remaining client can take ownership after the first client exits.
                self._connect()
                if self.service:
                    return getattr(self.service, name)(*args)
                return self._remote('/client/tool', {'method': name, 'args': list(args)})
        return invoke

    def close(self):
        if self.bridge:
            self.bridge.close()
            self.store.close()
