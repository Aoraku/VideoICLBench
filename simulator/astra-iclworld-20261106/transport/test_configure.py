import json
from pathlib import Path
import tempfile
import unittest

from configure import configure


class ConfigurationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.gate = self.root / "gate.json"

    def prepare(self, name="provider", scope="test", verified=True, url="https://api.example.invalid/v1"):
        configure(self.root/name, self.gate, self.root/"locks", scope, verified, url, "test-only")

    def test_gate_and_secret(self):
        self.prepare()
        self.prepare(name="second")
        self.assertEqual(json.loads(self.gate.read_text())["limit"], 50)
        self.assertEqual((self.root/"provider").stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((self.root/"provider").read_text())["codex"]["model"], "gpt-6-astra")
        with self.assertRaises(FileExistsError):
            self.prepare()
        with self.assertRaises(ValueError):
            self.prepare(name="third", scope="different")
        self.assertFalse((self.root/"third").exists())

    def test_unverified_or_non_tls(self):
        for kwargs in ({"verified": False}, {"url": "http://example.invalid/v1"},
                       {"url": "https://user@example.invalid/v1"}):
            with self.assertRaises(ValueError):
                self.prepare(**kwargs)
        self.assertFalse(self.gate.exists())
