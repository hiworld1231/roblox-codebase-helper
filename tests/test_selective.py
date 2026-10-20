"""Conditional reads, literal-search continuation and durable metadata resume."""
import unittest
from unittest.mock import patch

from test_context import ContextTests, SID, PLACE, metadata
from roblox_context.store import ContextError, Store


def view(result):
    return {k: result[k] for k in ('session', 'objectId', 'sourceHash', 'startLine', 'endLine')}


class SelectiveTests(unittest.TestCase):
    setUp = ContextTests.setUp
    tearDown = ContextTests.tearDown

    def test_search_scope_case_and_duplicates(self):
        extra = {**metadata()[-1], 'id': 'other', 'name': 'Main', 'parent': 'rs'}
        self.store.ingest(SID, 1, [extra])
        self.plugin.text['other'] = '-- PRIVATE-body outside'
        found = self.service.search(SID, 'private-body', search_in='source', scope_id='ss')
        self.assertEqual([i['objectId'] for i in found['items']], ['main'])
        self.assertEqual(found['items'][0]['matches'][0]['line'], 4)
        self.assertTrue(found['complete'])
        self.assertFalse(found['absenceConfirmed'])
        self.assertIsNone(self.store.source(SID, 'other'))
        self.assertEqual(self.service.builds, 0)
        with self.assertRaises(ContextError):
            self.service.search(SID, 'body', search_in='source')

    def test_search_twenty_scripts_and_cache_does_not_break_cursor(self):
        objects = [{"id": f's{i:02}', "name": "Script", "className": "Script", "parent": "ss"} for i in range(22)]
        self.store.ingest(SID, 1, objects)
        self.plugin.text.update({o['id']: '-- needle' for o in objects})
        first = self.service.search(SID, 'needle', search_in='source', scope_id='ss', limit=100)
        self.assertEqual(first['checkedScripts'], 20)
        self.assertFalse(first['complete'])
        second = self.service.search(SID, 'needle', search_in='source', scope_id='ss', limit=100, cursor=first['nextCursor'])
        self.assertTrue(second['complete'])
        self.assertEqual(sum(len(r['items']) for r in [first, second]), 22)
        self.assertFalse(second['absenceConfirmed'])
        reads = self.plugin.metrics['sourceReads']
        self.service.search(SID, 'needle', search_in='source', scope_id='ss', limit=100)
        self.assertEqual(self.plugin.metrics['sourceReads'], reads)

    def test_search_line_continuation_and_bounded_long_snippets(self):
        self.plugin.text['main'] = '\n'.join('x' * 400 + ' NEEDLE ' + str(n) for n in range(7))
        cursor, numbers = None, []
        for _ in range(7):
            result = self.service.search(SID, 'needle', search_in='source', scope_id='main', limit=2, cursor=cursor)
            for row in result['items']:
                for match in row['matches']:
                    numbers.append(match['line'])
                    self.assertIn('NEEDLE', match['snippet'])
                    self.assertLessEqual(len(match['snippet']), 180)
            cursor = result['nextCursor']
            if not cursor:
                break
        self.assertEqual(numbers, list(range(1, 8)))
        self.assertEqual(self.plugin.metrics['sourceReads'], 1)

    def test_search_cursor_invalidated_by_edits_query_and_scope(self):
        self.plugin.text['main'] = 'needle\nneedle\nneedle'
        result = self.service.search(SID, 'needle', search_in='source', scope_id='main', limit=1)
        for query, scope in [('other', 'main'), ('needle', 'ss')]:
            with self.assertRaises(ContextError):
                self.service.search(SID, query, search_in='source', scope_id=scope, cursor=result['nextCursor'])
        self.store.ingest(SID, 1, [{**metadata()[-1], 'sourceVersion': 1}])
        with self.assertRaises(ContextError):
            self.service.search(SID, 'needle', search_in='source', scope_id='main', cursor=result['nextCursor'])
        current = self.service.search(SID, 'needle', search_in='source', scope_id='main')
        self.assertEqual(current['matchLines'], 3)

    def test_search_failures_and_edits_during_read(self):
        with patch.object(self.plugin, 'source', side_effect=ContextError('plugin', 'inaccessible')):
            result = self.service.search(SID, 'needle', search_in='source', scope_id='main')
        self.assertEqual(len(result['unavailableSources']), 1)
        self.assertFalse(result['absenceConfirmed'])
        original = self.plugin.source
        def changing(sid, oid):
            result = original(sid, oid)
            self.store.ingest(SID, 1, [{**metadata()[-1], 'name': 'Moved'}])
            return result
        with patch.object(self.plugin, 'source', side_effect=changing), self.assertRaises(ContextError):
            self.service.search(SID, 'private', search_in='source', scope_id='main')

    def test_search_unicode_literal_and_empty_scope(self):
        self.plugin.text['main'] = '-- Straße [a.*] ' + 'x' * 300
        result = self.service.search(SID, 'STRASSE', search_in='source', scope_id='main')
        self.assertEqual(result['matchLines'], 1)
        self.assertEqual(self.service.search(SID, '[a.*]', search_in='source', scope_id='main')['matchLines'], 1)
        result = self.service.search(SID, 'missing', search_in='source', scope_id='remote')
        self.assertTrue(result['absenceConfirmed'])
        self.assertEqual(result['totalScripts'], 0)
        for bad in ('', '\n'):
            with self.assertRaises(ContextError):
                self.service.search(SID, bad, search_in='source', scope_id='main')

    def test_known_view_suppresses_only_covered_current_text(self):
        first = self.service.read(SID, 'main', 1, 3)
        known = view(first)
        repeated = self.service.read(SID, 'main', 2, 2, known_view=known)
        self.assertTrue(repeated['unchanged'])
        self.assertNotIn('lines', repeated)
        for hint in [dict(known, session='other'), dict(known, objectId='mod'), dict(known, sourceHash='old')]:
            self.assertIn('lines', self.service.read(SID, 'main', 2, 2, known_view=hint))
        self.assertIn('lines', self.service.read(SID, 'main', 3, 4, known_view=known))
        self.assertIn('lines', self.service.read(SID, 'main', 2, 2))

    def test_known_view_freshness_source_change_and_stale_revision(self):
        first = self.service.read(SID, 'main', 1, 3)
        self.store.ingest(SID, 1, [{**metadata()[-1], 'sourceVersion': 1}])
        self.plugin.text['main'] = '-- edited\nreturn 2'
        with self.assertRaises(ContextError):
            self.service.read(SID, 'main', 1, 2, expected_revision=first['revision'], known_view=view(first))
        current = self.service.read(SID, 'main', 1, 2, known_view=view(first))
        self.assertEqual(current['lines'][0]['text'], '-- edited')
        self.store.mark_stale(SID)
        with self.assertRaises(ContextError):
            self.service.read(SID, 'main', 1, 2, known_view=view(current))

    def test_resume_coalesces_rename_move_delete_and_parent_paths(self):
        self.service.checkpoint(SID, {'task': 'Resume', 'checks': ['recorded assertion']})
        self.store.ingest(SID, 1, [{**metadata()[1], 'name': 'RenamedStorage'}])
        self.store.ingest(SID, 2, [{**metadata()[3], 'parent': 'ss'}])
        self.store.ingest(SID, 3, [], ['mod'])
        with patch.object(self.plugin, 'source', side_effect=AssertionError('resume must not read code')):
            result = self.service.overview(SID, resume=True)
        item = next(i for i in result['items'] if i['objectId'] == 'mod')
        self.assertEqual(item['beforePath'], 'game.ReplicatedStorage.Config')
        self.assertIsNone(item['currentPath'])
        self.assertEqual(item['lastChange'], 'removed')
        self.assertEqual(item['events'], 3)
        self.assertTrue(item['pathsConfirmed'])
        self.assertIn('not automatically', result['checksStatus'])
        self.assertEqual(self.store.changes(SID, 1)[0].keys(), {'revision', 'added', 'removed', 'changed'})

    def test_resume_pages_no_checkpoint_repeat_and_legacy_history(self):
        self.service.checkpoint(SID, {'task': 'Resume'})
        self.store.ingest(SID, 1, [{**metadata()[1], 'name': 'Rename'}])
        result = self.service.overview(SID, resume=True, limit=1)
        self.assertIn('checkpoint', result)
        second = self.service.overview(SID, resume=True, limit=1, cursor=result['nextCursor'])
        self.assertNotIn('checkpoint', second)
        self.assertNotEqual(result['items'], second['items'])
        with self.store.lock, self.store.db:
            self.store._record(SID, {'changed': ['main']})
        with self.assertRaises(ContextError):
            self.service.overview(SID, resume=True, cursor=result['nextCursor'])
        item = next(i for i in self.service.overview(SID, resume=True)['items'] if i['objectId'] == 'main')
        self.assertFalse(item['pathsConfirmed'])
        self.assertIsNone(item['beforePath'])

    def test_resume_no_checkpoint_offline_session_and_restart(self):
        self.assertEqual(self.service.overview(SID, resume=True)['changesStatus'], 'no_checkpoint')
        with self.assertRaises(ContextError):
            self.service.overview(resume=True)
        self.service.checkpoint(SID, {'task': 'Persist'})
        self.store.mark_stale(SID)
        result = self.service.overview(SID, resume=True)
        self.assertFalse(result['fresh'])
        self.assertEqual(result['checkpoint']['task'], 'Persist')
        self.assertEqual(result['changesStatus'], 'unavailable')
        self.store.close()
        self.store = Store(self.root, PLACE)
        self.service.store = self.plugin.store = self.store
        self.assertEqual(self.service.overview(SID, resume=True)['checkpoint']['task'], 'Persist')
        other = 'second-session'
        self.store.hello(other, PLACE, 'other-job', 'Untitled')
        self.store.ingest(other, 0, metadata(), snapshot=True)
        self.assertIsNone(self.service.overview(other, resume=True)['checkpoint'])

    def test_search_and_resume_budget(self):
        self.plugin.text['main'] = '\n'.join('-- needle ' + 'x' * 170 for _ in range(90))
        cursor, found = None, []
        for _ in range(100):
            result = self.service.search(SID, 'needle', search_in='source', scope_id='main', cursor=cursor, budget=650)
            self.assertLessEqual(result['estimatedTokens'], 650)
            found += [m['line'] for row in result['items'] for m in row['matches']]
            cursor = result['nextCursor']
            if not cursor: break
        self.assertEqual(found, list(range(1, 91)))
        self.service.checkpoint(SID, {'task': 'x'})
        self.store.ingest(SID, 1, [{**metadata()[1], 'name': 'changed'}])
        result = self.service.overview(SID, resume=True, budget=650)
        self.assertLessEqual(result['estimatedTokens'], 650)


del ContextTests
