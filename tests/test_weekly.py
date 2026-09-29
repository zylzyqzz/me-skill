import copy
import json
from pathlib import Path
import shutil
import os
import subprocess
import sys
import tempfile
import unittest
from fixtures import seed

from unittest.mock import patch
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import me
import profile_store as storage
import submit_pr
import configure
REPO="example-owner/private-assistant"
PREFIX="/repos/"+REPO


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "references").mkdir()
        shutil.copy2(ROOT / "references" / "profile.json", self.root / "references" / "profile.json")
        shutil.copy2(ROOT / "me.json", self.root / "me.json")
        configure.configure(self.root, REPO, "Synthetic", "UTC", True)
        storage.atomic_write(self.root / "references" / "profile.json", seed())
        self.identity = me.init(self.root, "test-ai")
        self.now = datetime(2026, 9, 28, 9, tzinfo=timezone.utc)

    def change(self, rid="weekly-format"):
        local = storage.read_json(self.root / ".local" / "profile.json")
        record = {"id": rid, "topic": "报告", "statement": "以后周报用表格。", "use": "周报采用表格。",
                  "scope": "weekly-report", "status": "confirmed", "reviewed_on": "2026-09-28",
                  "evidence": [{"kind": "direct_user", "reference": "synthetic-user-message-1",
                                "summary": "Synthetic user explicitly requests tables for weekly reports"}]}
        patch = {"expected_revision": local["revision"], "reason": "Synthetic correction", "upsert": [record]}
        storage.mutate(self.root / ".local" / "profile.json", "apply", local["revision"], True, patch=patch)
        return record

    def review_input(self):
        import weekly_review
        return {**weekly_review.window(self.now),
                "coverage": {"status": "partial", "sources": ["synthetic-session"],
                             "sessions_reviewed": 1, "limitations": ["Synthetic fixture only"]},
                "evidence": [{"id": "e1", "at": (self.now - timedelta(hours=1)).isoformat(),
                              "source": "synthetic-session", "summary": "Synthetic user correction"}],
                "activities": [{"summary": "Synthetic task review", "evidence_ids": ["e1"]}],
                "habits": [{"summary": "Synthetic scoped preference", "assessment": "confirmed", "evidence_ids": ["e1"]}],
                "profile_evidence": {x["id"]: ["e1"] for x in me.due(self.root, self.now)["pending"]}}

    def prepare(self, **kwargs):
        return me.prepare(self.root, self.now, review=self.review_input(), **kwargs)

    def test_init_is_idempotent(self):
        self.assertEqual(self.identity, me.init(self.root, "different-ai"))

    def test_full_submit_roundtrip_uses_configured_owner_and_me_branch(self):
        import base64
        output = self.prepare()
        bundle = storage.read_json(output["bundle"])
        branch = output["head"]
        remote_path = output["remote_path"]
        remote = {}
        def fake_api(path, method="GET", data=None, missing_ok=False, *, repository):
            self.assertEqual(repository, REPO)
            self.assertTrue(path.startswith(PREFIX))
            if path == PREFIX:
                return {"full_name": REPO, "private": True, "permissions": {"push": True}}
            if "/pulls?" in path:
                return []
            if "/git/ref/heads/main" in path:
                return {"object": {"sha": "synthetic-main"}}
            if "/git/ref/heads/" in path:
                return None
            if path.endswith('/git/refs'):
                self.assertEqual(data['ref'], 'refs/heads/' + branch)
                self.assertTrue(branch.startswith('me/'))
                return {}
            if '/contents/' in path:
                if method == 'PUT':
                    remote.update(data)
                    return {}
                return {'content': remote['content'], 'sha': 'synthetic-file'} if remote else None
            if path.endswith('/pulls'):
                self.assertEqual(data['head'], branch)
                return {'number': 7}
            if '/pulls/7/files' in path:
                return [{'filename': remote_path}]
            if path.endswith('/pulls/7'):
                return {'base': {'ref': 'main'}, 'head': {'ref': branch, 'sha': 'synthetic-head'},
                        'html_url': 'https://github.com/' + REPO + '/pull/7'}
            self.fail('Unexpected endpoint')
        with patch.object(submit_pr, 'api', side_effect=fake_api):
            result = submit_pr.submit(self.root, output['bundle'], True)
        self.assertTrue(result['verified'])
        self.assertEqual(json.loads(base64.b64decode(remote['content'])), bundle)
        self.assertFalse(me.due(self.root, self.now)['review_due'])

    def test_bundle_cannot_reroute_submission_to_other_owner(self):
        output = self.prepare()
        bundle = storage.read_json(output['bundle'])
        bundle['repository'] = 'another-owner/private-assistant'
        storage.atomic_write(Path(output['bundle']), bundle)
        with patch.object(submit_pr, 'api') as api:
            with self.assertRaisesRegex(ValueError, 'differs from local configuration'):
                submit_pr.submit(self.root, output['bundle'], True)
            api.assert_not_called()

    def test_failed_remote_write_does_not_acknowledge(self):
        output = self.prepare()
        def fake_api(path, method="GET", data=None, missing_ok=False, *, repository):
            if path == PREFIX:
                return {"full_name": REPO, "private": True, "permissions": {"push": True}}
            if '/pulls?' in path:
                return []
            if '/git/ref/heads/main' in path:
                return {'object': {'sha': 'synthetic-main'}}
            if '/git/ref/heads/' in path:
                return None
            if method != 'GET':
                raise ValueError('Synthetic network failure')
            self.fail('Unexpected endpoint')
        with patch.object(submit_pr, 'api', side_effect=fake_api):
            with self.assertRaisesRegex(ValueError, 'network failure'):
                submit_pr.submit(self.root, output['bundle'], True)
        self.assertTrue(me.due(self.root, self.now)['review_due'])

    def test_review_required_even_if_old_local_evidence_exists(self):
        self.change()
        with self.assertRaisesRegex(ValueError, "weekly review is required"):
            me.prepare(self.root, self.now)

    def test_activity_without_profile_change_can_be_submitted(self):
        output = self.prepare()
        bundle = storage.read_json(output["bundle"])
        self.assertEqual(bundle["schema_version"], 2)
        self.assertEqual(bundle["observations"], [])
        self.assertIn("本周使用情况", Path(output["body_file"]).read_text(encoding="utf-8"))

    def test_unavailable_history_is_not_no_activity(self):
        review = self.review_input()
        review.update(evidence=[], activities=[], habits=[], profile_evidence={})
        review["coverage"].update(status="unavailable", sources=[], sessions_reviewed=0)
        result = me.prepare(self.root, self.now, review=review)
        self.assertEqual(result["reason"], "history-unavailable")
        self.assertTrue(result["needs_attention"])

    def test_review_time_sources_and_coverage_rejected(self):
        changes = [
            (lambda r: r["evidence"][0].update(at=self.now.isoformat()), "outside review window"),
            (lambda r: r["evidence"][0].update(source="unknown"), "Unknown evidence source"),
            (lambda r: r["activities"][0].update(evidence_ids=["missing"]), "Unknown or duplicate"),
            (lambda r: r["coverage"].update(limitations=[]), "Empty limitations"),
            (lambda r: r.update(period_start=self.now.isoformat()), "preceding seven days"),
            (lambda r: r["habits"][0].update(summary="contact person@example.test"), "email-address"),
            (lambda r: r.update(profile_evidence={"unknown-record": ["e1"]}), "non-pending"),
        ]
        for mutate, message in changes:
            with self.subTest(message=message):
                review = self.review_input()
                mutate(review)
                with self.assertRaisesRegex(ValueError, message):
                    me.prepare(self.root, self.now, review=review)

    def test_old_accumulated_evidence_is_not_implicitly_included(self):
        self.change()
        review = self.review_input()
        review["profile_evidence"] = {}
        result = me.prepare(self.root, self.now, review=review)
        self.assertEqual(storage.read_json(result["bundle"])["observations"], [])

    def test_legacy_proposal_readable_but_not_newly_submittable(self):
        self.change()
        output = self.prepare()
        bundle = storage.read_json(output["bundle"])
        bundle.pop("review")
        bundle["schema_version"] = 1
        self.assertEqual(me.validate_proposal(bundle)["schema_version"], 1)
        storage.atomic_write(Path(output["bundle"]), bundle)
        with patch.object(submit_pr, "api") as api:
            with self.assertRaisesRegex(ValueError, "trigger-time weekly review"):
                submit_pr.submit(self.root, output["bundle"], True)
            api.assert_not_called()

    def test_summary_only_receipt_deduplicates_and_checks_review_hash(self):
        output = self.prepare()
        url = "https://github.com/example-owner/private-assistant/pull/2"
        me.acknowledge(self.root, output["bundle"], url)
        self.assertFalse(me.review_plan(self.root, self.now)["review_due"])
        bundle = storage.read_json(output["bundle"])
        bundle["review"]["activities"][0]["summary"] = "Different synthetic activity"
        storage.atomic_write(Path(output["bundle"]), bundle)
        with patch.object(submit_pr, "api") as api:
            with self.assertRaisesRegex(ValueError, "already submitted different"):
                submit_pr.submit(self.root, output["bundle"], True)
            api.assert_not_called()

    def test_no_evidence_no_pr(self):
        self.assertFalse(me.due(self.root, self.now)["due"])
        self.assertTrue(me.review_plan(self.root, self.now)["review_due"])
        review = self.review_input()
        review.update(evidence=[], activities=[], habits=[], profile_evidence={})
        review["coverage"].update(status="complete", sessions_reviewed=0, limitations=[])
        result = me.prepare(self.root, self.now, review=review)
        self.assertFalse(result["prepared"])
        self.assertEqual(result["reason"], "no-observed-activity")

    def test_source_baseline_not_modified_by_learning(self):
        before = (self.root / "references" / "profile.json").read_bytes()
        self.change()
        self.assertEqual(before, (self.root / "references" / "profile.json").read_bytes())

    def test_prepare_does_not_mark_submitted(self):
        self.change()
        output = self.prepare()
        self.assertTrue(output["prepared"])
        self.assertTrue(me.due(self.root, self.now)["due"])
        self.assertEqual(storage.read_json(output["bundle"])["observations"][0]["record"]["scope"], "weekly-report")

    def test_acknowledgment_and_same_week_dedup(self):
        self.change()
        bundle = self.prepare()
        url = "https://github.com/example-owner/private-assistant/pull/1"
        me.acknowledge(self.root, bundle["bundle"], url)
        self.assertTrue(me.acknowledge(self.root, bundle["bundle"], url)["unchanged"])
        self.change("another-weekly-preference")
        self.assertFalse(me.due(self.root, self.now)["due"])
        self.assertNotIn("prepared", self.prepare(immediate=True))
        later = datetime(2026, 10, 5, 9, tzinfo=timezone.utc)
        self.assertEqual(me.due(self.root, later)["pending_count"], 1)
        self.assertTrue(me.due(self.root, later)["due"])

    def test_wrong_repository_ack_rejected(self):
        self.change()
        bundle = self.prepare()
        with self.assertRaisesRegex(ValueError, "configured repository"):
            me.acknowledge(self.root, bundle["bundle"], "https://github.com/other/repo/pull/1")

    def test_uploaded_bundle_cannot_belong_to_other_installation(self):
        self.change()
        output = self.prepare()
        bundle = storage.read_json(output["bundle"])
        bundle["agent_id"] = "different-installation"
        storage.atomic_write(Path(output["bundle"]), bundle)
        with self.assertRaisesRegex(ValueError, "another installation"):
            me.acknowledge(self.root, output["bundle"], "https://github.com/example-owner/private-assistant/pull/1")

    def test_remote_conflict_not_silently_applied(self):
        self.change("language")
        canonical_path = self.root / "references" / "profile.json"
        canonical = storage.read_json(canonical_path)
        rec = next(r for r in canonical["records"] if r["id"] == "language")
        rec["statement"] = "Upstream approved a different language preference"
        storage.atomic_write(canonical_path, canonical)
        report = me.view(self.root)
        self.assertEqual(report["conflicts"][0]["id"], "language")
        self.assertEqual(next(r for r in report["records"] if r["id"] == "language")["statement"], rec["statement"])

    def test_merged_preference_not_resubmitted(self):
        rec = self.change()
        canonical_path = self.root / "references" / "profile.json"
        canonical = storage.read_json(canonical_path)
        canonical["records"].append(rec)
        storage.atomic_write(canonical_path, canonical)
        self.assertEqual(me.due(self.root, self.now)["pending_count"], 0)

    def test_privacy_patterns_block_outbox(self):
        rec = self.change()
        local_path = self.root / ".local" / "profile.json"
        local = storage.read_json(local_path)
        next(r for r in local["records"] if r["id"] == rec["id"])["evidence"][0]["summary"] = "contact person@example.test"
        storage.atomic_write(local_path, local)
        with self.assertRaisesRegex(ValueError, "email-address"):
            self.prepare()
        self.assertFalse((self.root / ".local" / "outbox").exists())

    def test_two_installs_have_distinct_branches(self):
        self.change()
        first = self.prepare()
        with tempfile.TemporaryDirectory() as other:
            other_root = Path(other)
            (other_root / "references").mkdir()
            shutil.copy2(self.root / "references" / "profile.json", other_root / "references" / "profile.json")
            shutil.copy2(self.root / "me.json", other_root / "me.json")
            identity = me.init(other_root, "test-ai")
            self.assertNotEqual(identity["agent_id"], self.identity["agent_id"])
            self.assertIn(self.identity["agent_id"], first["head"])

    def test_forget_removes_local_and_generates_deletion(self):
        me.forget(self.root, ["language"], me.state(self.root)[2]["revision"], True)
        self.assertNotIn("language", [r["id"] for r in me.view(self.root)["records"]])
        self.assertNotIn("language", [r["id"] for r in storage.read_json(self.root / ".local" / "baseline.json")["records"]])
        prepared = self.prepare()
        observation = storage.read_json(prepared["bundle"])["observations"][0]
        self.assertEqual(observation["operation"], "delete")
        self.assertNotIn("record", observation)

    def test_iso_year_boundary(self):
        self.assertEqual(me.week(datetime(2027, 1, 1, tzinfo=timezone.utc)), "2026-W53")

    def test_cli_outputs_unicode_even_with_ascii_host(self):
        commands = [
            [sys.executable, str(ROOT / "scripts" / "me.py"), "--root", str(self.root), "view"],
            [sys.executable, str(ROOT / "scripts" / "profile_store.py"), "--store",
             str(self.root / ".local" / "profile.json"), "show"]]
        for command in commands:
            with self.subTest(script=command[1]):
                result = subprocess.run(command, capture_output=True, env=dict(os.environ, PYTHONIOENCODING="ascii"))
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
                self.assertIn("中文", result.stdout.decode("utf-8"))

    def test_submit_preview_only_reads_remote(self):
        self.change()
        bundle = self.prepare()
        def fake_api(path, method="GET", data=None, missing_ok=False, *, repository):
            self.assertEqual(repository, REPO)
            self.assertEqual(method, "GET")
            if path == PREFIX:
                return {"full_name": REPO, "private": True, "permissions": {"push": True}}
            if "/pulls?" in path:
                return []
            if "/git/ref/" in path:
                return None
            self.fail("Unexpected endpoint")
        with patch.object(submit_pr, "api", side_effect=fake_api):
            result = submit_pr.submit(self.root, bundle["bundle"])
        self.assertTrue(result["ready"])
        self.assertFalse(result["written"])
        self.assertTrue(me.due(self.root, self.now)["due"])

    def test_submit_refuses_public_repository(self):
        self.change()
        bundle = self.prepare()
        with patch.object(submit_pr, "api", return_value={"full_name": REPO, "private": False}):
            with self.assertRaisesRegex(ValueError, "remain private"):
                submit_pr.submit(self.root, bundle["bundle"], True)

    def test_submit_refuses_unrelated_branch_changes(self):
        self.change()
        bundle = self.prepare()
        def fake_api(path, method="GET", data=None, missing_ok=False, *, repository):
            self.assertEqual(repository, REPO)
            self.assertEqual(method, "GET")
            if path == PREFIX:
                return {"full_name": REPO, "private": True, "permissions": {"push": True}}
            if "/pulls?" in path:
                return []
            if "/git/ref/" in path:
                return {"object": {"sha": "synthetic"}}
            if "/compare/" in path:
                return {"files": [{"filename": "SKILL.md"}]}
            self.fail("Unexpected endpoint")
        with patch.object(submit_pr, "api", side_effect=fake_api):
            with self.assertRaisesRegex(ValueError, "unrelated"):
                submit_pr.submit(self.root, bundle["bundle"], True)

    def test_submit_body_privacy_checked_before_remote(self):
        self.change()
        bundle = self.prepare()
        Path(bundle["body_file"]).write_text("private contact person@example.test", encoding="utf-8")
        with patch.object(submit_pr, "api") as api:
            with self.assertRaisesRegex(ValueError, "email-address"):
                submit_pr.submit(self.root, bundle["bundle"], True)
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
