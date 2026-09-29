import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from fixtures import seed


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import onboard
import me
import configure
import profile_store as storage


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "skill"
        (self.root / "references").mkdir(parents=True)
        for name in ("profile.json", "context.md"):
            shutil.copy2(ROOT / "references" / name, self.root / "references" / name)
        shutil.copy2(ROOT / "me.json", self.root / "me.json")
        configure.configure(self.root, "example-owner/private-assistant", "Synthetic", "UTC", True)
        storage.atomic_write(self.root / "references" / "profile.json", seed())
        me.init(self.root, "synthetic")
        self.target = self.base / "AGENTS.md"
        self.original = "Existing unrelated user rules\r\n保持原文。\r\n".encode("utf-8")
        self.target.write_bytes(self.original)

    def test_dry_run_is_read_only(self):
        result = onboard.install(self.root, self.target)
        self.assertTrue(result["changed"])
        self.assertFalse(result["written"])
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertFalse((self.root / ".local" / "onboarding.json").exists())

    def test_install_preserves_rules_backs_up_and_is_idempotent(self):
        result = onboard.install(self.root, self.target, True)
        self.assertEqual(Path(result["backup"]).read_bytes(), self.original)
        first = self.target.read_bytes()
        self.assertTrue(first.startswith(self.original))
        second = onboard.install(self.root, self.target, True)
        self.assertFalse(second["changed"])
        self.assertEqual(first, self.target.read_bytes())
        self.assertFalse(second["new_session_verified"])

    def test_update_only_replaces_owned_block(self):
        onboard.install(self.root, self.target, True)
        with self.target.open("ab") as handle:
            handle.write(b"\nLater user rules\r\n")
        settings = json.loads((self.root / "me.json").read_text(encoding="utf-8"))
        settings["version"] = "1.1.1"
        (self.root / "me.json").write_text(json.dumps(settings), encoding="utf-8")
        onboard.install(self.root, self.target, True)
        updated = self.target.read_bytes()
        self.assertTrue(updated.startswith(self.original))
        self.assertTrue(updated.endswith(b"\nLater user rules\r\n"))
        self.assertEqual(updated.count(onboard.BEGIN.encode()), 1)
        self.assertIn(b"1.1.1", updated)

    def test_context_is_self_contained_and_separates_candidates(self):
        text = onboard.render(self.root)
        for expected in ("Synthetic", "中文", "用户级全局", "最近 7 天", "待核实背景"):
            self.assertIn(expected, text)

    def test_malformed_block_and_size_limit_protect_user_file(self):
        for content in (self.original + onboard.BEGIN.encode(), b"x" * 24576):
            self.target.write_bytes(content)
            with self.assertRaises(ValueError):
                onboard.install(self.root, self.target, True)
            self.assertEqual(self.target.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
