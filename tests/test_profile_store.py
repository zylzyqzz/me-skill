import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from fixtures import seed

from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("profile_store", ROOT / "scripts" / "profile_store.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProfileStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "profile.json"
        self.initial = seed()
        # A fresh synthetic store keeps revision tests independent of package releases.
        self.initial["revision"] = 0
        self.initial["history"] = []
        self.path.write_text(json.dumps(self.initial, ensure_ascii=False), encoding="utf-8")
        self.rec = copy.deepcopy(self.initial["records"][1])
        self.rec["statement"] = "以后默认用英文。"
        self.rec["evidence"] = [{"kind": "direct_user", "reference": "test-user-message-1",
                                 "summary": "Synthetic user says default to English"}]
        self.payload = {"expected_revision": 0, "reason": "Explicit synthetic user correction",
                        "upsert": [self.rec]}

    def apply(self, write=True, payload=None):
        payload = self.payload if payload is None else payload
        return module.mutate(self.path, "apply", payload["expected_revision"], write, patch=payload)

    def test_seed_schema(self):
        module.validate(self.initial)

    def test_preview_does_not_write(self):
        before = self.path.read_bytes()
        self.assertFalse(self.apply(write=False)["written"])
        self.assertEqual(before, self.path.read_bytes())

    def test_correction_and_rollback(self):
        self.apply()
        saved = module.read_json(self.path)
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(saved["records"][1]["statement"], "以后默认用英文。")
        module.mutate(self.path, "rollback", 1, True, target=0)
        saved = module.read_json(self.path)
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(saved["records"], self.initial["records"])

    def test_stale_writer_rejected(self):
        self.apply()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Revision conflict"):
            self.apply()
        self.assertEqual(before, self.path.read_bytes())

    def test_inference_cannot_be_confirmed(self):
        self.payload["upsert"][0]["evidence"][0]["kind"] = "inference"
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "confirmed requires"):
            self.apply()
        self.assertEqual(before, self.path.read_bytes())

    def test_repeated_same_historical_source_not_independent(self):
        evidence = self.payload["upsert"][0]["evidence"][0]
        evidence["kind"] = "historical_user"
        self.payload["upsert"][0]["evidence"].append(copy.deepcopy(evidence))
        with self.assertRaisesRegex(ValueError, "confirmed requires"):
            self.apply()

    def test_independent_historical_sources_accepted(self):
        evidence = self.payload["upsert"][0]["evidence"][0]
        evidence["kind"] = "historical_user"
        other = copy.deepcopy(evidence)
        other["reference"] = "test-user-message-2"
        self.payload["upsert"][0]["evidence"].append(other)
        self.assertTrue(self.apply()["written"])

    def test_invalid_patch_does_not_write(self):
        self.payload["upsert"][0]["status"] = "unknown"
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Invalid status"):
            self.apply()
        self.assertEqual(before, self.path.read_bytes())

    def test_lock_blocks_other_writer(self):
        lock = self.path.with_suffix(".json.lock")
        lock.write_text("another writer", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "locked"):
            self.apply()
        self.assertTrue(lock.exists())

    def test_forget_scrubs_history_and_cannot_be_undone(self):
        self.apply()
        module.mutate(self.path, "forget", 1, True, ids=["language"])
        saved = module.read_json(self.path)
        for records in [saved["records"]] + [s["records"] for s in saved["history"]]:
            self.assertNotIn("language", [r["id"] for r in records])
            self.assertNotIn("以后默认用英文。", json.dumps(records, ensure_ascii=False))
        # Change another record so rollback to scrubbed revision zero has an effect.
        rec = copy.deepcopy(saved["records"][0])
        rec["use"] += " Additional synthetic rule."
        self.apply(payload={"expected_revision": 2, "reason": "Synthetic change", "upsert": [rec]})
        module.mutate(self.path, "rollback", 3, True, target=0)
        self.assertNotIn("language", [r["id"] for r in module.read_json(self.path)["records"]])

    def test_failed_atomic_replace_preserves_original(self):
        before = self.path.read_bytes()
        with patch.object(module.os, "replace", side_effect=OSError("synthetic replace failure")):
            with self.assertRaises(OSError):
                self.apply()
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse(self.path.with_suffix(".json.lock").exists())
        self.assertEqual(list(self.path.parent.glob(".profile-*.tmp")), [])

    def test_noop_does_not_create_revision(self):
        self.payload["upsert"] = [copy.deepcopy(self.initial["records"][0])]
        with self.assertRaisesRegex(ValueError, "No new evidence"):
            self.apply()

    def test_duplicate_ids_rejected(self):
        self.payload["upsert"].append(copy.deepcopy(self.rec))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.apply()


if __name__ == "__main__":
    unittest.main(verbosity=2)
