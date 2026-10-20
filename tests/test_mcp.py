"""Actual MCP SDK stdio client; zero model requests and isolated temporary state."""
import asyncio
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from roblox_context.__main__ import main
from test_context import SID, PLACE, metadata


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_workflow_metadata_source_graph_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            main(["--root", str(root), "init", "--port", str(port)])
            token = json.loads((root / ".context/config.json").read_text())["token"]
            def post(route, value):
                req = urllib.request.Request("http://127.0.0.1:" + str(port) + route, data=json.dumps(value).encode(), headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=3) as response:
                    return json.load(response)
            params = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).resolve().parents[1] / "scripts/run.py"), "--root", str(root), "serve"])
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertEqual(len(tools.tools), 7)
                    async def call(name, **args):
                        result = await session.call_tool(name, args)
                        self.assertFalse(result.isError)
                        text = result.content[0].text
                        self.assertNotIn("\n", text)
                        return json.loads(text)
                    self.assertEqual((await call("project_overview"))["sessions"], [])
                    post("/hello", {"session": SID, "placeId": PLACE, "jobId": "test-job", "name": "Untitled"})
                    post("/snapshot/begin", {"session": SID, "seq": 0})
                    post("/snapshot/chunk", {"session": SID, "items": metadata()})
                    post("/snapshot/end", {"session": SID, "count": 6})
                    stop = threading.Event()
                    failures = []
                    def plugin():
                        try:
                            while not stop.wait(.02):
                                commands = post("/poll", {"session": SID, "seq": 0})["commands"]
                                for command in commands:
                                    value = {"session": SID, "seq": 0, "requestId": command["requestId"]}
                                    if command["kind"] == "source":
                                        value.update(version=0, source='local R = game:GetService("ReplicatedStorage")\nrequire(R.Config)\n-- private' if command["id"] == "main" else "return {}")
                                    post("/result", value)
                        except Exception as exc:
                            failures.append(str(exc))
                    worker = threading.Thread(target=plugin)
                    worker.start()
                    try:
                        result = await call("project_search", session_id=SID, text="Config")
                        self.assertEqual(result["items"][0]["id"], "mod")
                        self.assertEqual(result["coverage"]["indexedScripts"], 0)
                        result = await call("get_context", session_id=SID, object_ids=["main"])
                        self.assertEqual(result["coverage"]["indexedScripts"], 2)
                        self.assertNotIn("-- private", json.dumps(result))
                        result = await call("read_source", session_id=SID, object_id="main", start_line=2, end_line=2)
                        self.assertEqual(result["lines"][0]["text"], "require(R.Config)")
                        known = {k: result[k] for k in ("session", "objectId", "sourceHash", "startLine", "endLine")}
                        same = await call("read_source", session_id=SID, object_id="main", start_line=2, end_line=2, known_view=known)
                        self.assertTrue(same["unchanged"])
                        hits = await call("project_search", session_id=SID, text="PRIVATE", search_in="source", scope_id="ss")
                        self.assertEqual(hits["items"][0]["objectId"], "main")
                        self.assertTrue(hits["complete"])
                        result = await call("task_checkpoint", session_id=SID, record={"task": "Continue test", "checks": ["MCP stdio"]})
                        self.assertEqual(result["checkpoint"]["task"], "Continue test")
                        resumed = await call("project_overview", session_id=SID, resume=True)
                        self.assertEqual(resumed["checkpoint"]["task"], "Continue test")
                        self.assertEqual(resumed["items"], [])
                        self.assertNotIn("-- private", json.dumps(resumed))
                        self.assertTrue((root / "projects" / str(PLACE) / SID / "docs/CURRENT_TASK.md").exists())
                    finally:
                        stop.set()
                        worker.join(timeout=3)
                    self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
