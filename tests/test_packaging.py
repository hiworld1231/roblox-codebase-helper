"""No-Rojo packaging and filesystem metadata-index lifecycle."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from tree_sitter import Language, Parser
import tree_sitter_luau

from roblox_context.__main__ import build_plugin, main

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("index_generator", ROOT / "scripts/generate_index.py")
index_generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(index_generator)


class PackagingTests(unittest.TestCase):
    def test_public_xml_has_no_token_and_native_luau_syntax(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "Plugin.rbxmx"
            build_plugin(Path(temporary), output)
            source = ET.parse(output).find("./Item/Properties/ProtectedString").text
            self.assertIn('token = ""', source)
            self.assertNotIn("__CONTEXT_CONFIG__", source)
            self.assertLess(source.index("game.PlaceId ~= config.placeId"), source.index('game:GetService('))
            self.assertNotIn("UpdateSourceAsync", source)
            self.assertFalse(Parser(Language(tree_sitter_luau.language())).parse(source.encode()).root_node.has_error)

    def test_private_build_credentials_are_private_and_init_refuses_replace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            main(["--root", str(root), "init"])
            config = root / ".context/config.json"
            before = config.read_bytes()
            with self.assertRaises(SystemExit):
                main(["--root", str(root), "init"])
            self.assertEqual(config.read_bytes(), before)
            output = root / ".context/plugin.rbxmx"
            build_plugin(root, output, private=True)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_local_index_add_delete_rename_without_reading_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "plugin").mkdir()
            entry = root / "plugin/ContextPlugin.luau"
            entry.write_text("-- MUST NOT BE READ")
            first = index_generator.local_index(root)
            other = root / "plugin/New.luau"
            other.write_text("-- MUST NOT BE READ")
            with patch.object(Path, "read_text", side_effect=AssertionError("Source body read")):
                second = index_generator.local_index(root)
                other.rename(root / "plugin/Renamed.luau")
                third = index_generator.local_index(root)
                (root / "plugin/Renamed.luau").unlink()
                fourth = index_generator.local_index(root)
            self.assertNotEqual(first, second)
            self.assertNotEqual(second, third)
            self.assertNotIn("New.luau", third)
            self.assertIn("unmapped", third)
            self.assertEqual(first, fourth)


if __name__ == "__main__":
    unittest.main()
