"""Portable local learning and weekly PR preparation. Never performs network requests."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from uuid import uuid4

import profile_store as storage
import weekly_review

ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def week(now=None):
    now = now or datetime.now(timezone.utc)
    storage.require(now.tzinfo is not None, "Timestamp needs a timezone")
    iso = now.astimezone(timezone.utc).isocalendar()
    return f"{iso.year}-W{iso.week:02}"


def repository_name(value):
    storage.require(isinstance(value, str) and
                    re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+", value) is not None and
                    value.split("/")[1] not in (".", ".."), "Configure your own owner/repository first")
    return value


def config(root, allow_unconfigured=False):
    data = storage.read_json(root / "me.json")
    storage.require(data["name"] == "me-skill" and data["base_branch"] == "main" and
                    data["visibility"] == "private", "Unexpected installation policy")
    if not allow_unconfigured or data.get("repository") is not None:
        repository_name(data.get("repository"))
        storage.require(data["repository"].lower() != "zylzyqzz/me-skill",
                        "The public template cannot store personal profiles or weekly proposals")
        storage.require(isinstance(data.get("display_name"), str) and data["display_name"].strip(),
                        "Configure the current user's display name")
        storage.require(isinstance(data.get("timezone"), str) and data["timezone"].strip(),
                        "Configure the user's confirmed timezone")
    return data


def init(root, platform="generic"):
    config(root)
    storage.require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", platform) is not None,
                    "Use an anonymous lowercase platform label")
    local = root / ".local"
    local.mkdir(exist_ok=True)
    lock = local / "init.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("Initialization locked; inspect the active writer") from None
    os.close(fd)
    try:
        if (local / "agent.json").exists():
            storage.require((local / "baseline.json").exists() and (local / "profile.json").exists(),
                            "Incomplete local installation; preserve files and repair explicitly")
            return storage.read_json(local / "agent.json")
        baseline = storage.validate(storage.read_json(root / "references" / "profile.json"))
        storage.require(not (local / "profile.json").exists() and not (local / "baseline.json").exists(),
                        "Partial initialization exists; inspect before overwriting")
        storage.atomic_write(local / "baseline.json", baseline)
        storage.atomic_write(local / "profile.json", baseline)
        identity = {"agent_id": platform + "-" + uuid4().hex[:10], "platform": platform,
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "submissions": [], "deletions": {}}
        storage.atomic_write(local / "agent.json", identity)
        return identity
    finally:
        lock.unlink()


def state(root):
    local = root / ".local"
    storage.require((local / "agent.json").exists(), "Run init first")
    return (storage.read_json(local / "agent.json"),
            storage.validate(storage.read_json(local / "baseline.json")),
            storage.validate(storage.read_json(local / "profile.json")),
            storage.validate(storage.read_json(root / "references" / "profile.json")))


def observations(root):
    identity, baseline, local, canonical = state(root)
    base = {r["id"]: r for r in baseline["records"]}
    current = {r["id"]: r for r in local["records"]}
    upstream = {r["id"]: r for r in canonical["records"]}
    result = []
    for rid, rec in current.items():
        if rec == base.get(rid) or rec == upstream.get(rid) or rid in identity["deletions"]:
            continue
        result.append({"operation": "upsert", "id": rid, "record": rec,
                       "base_record_hash": digest(base[rid]) if rid in base else None,
                       "conflict": upstream.get(rid) != base.get(rid)})
    for rid, old_hash in identity["deletions"].items():
        if rid in upstream:
            result.append({"operation": "delete", "id": rid, "base_record_hash": old_hash,
                           "conflict": digest(upstream[rid]) != old_hash})
    return identity, canonical, result


def view(root):
    identity, canonical, observed = observations(root)
    effective = {r["id"]: r for r in canonical["records"]}
    conflicts = []
    for entry in observed:
        if entry["operation"] == "delete":
            effective.pop(entry["id"], None)
        elif entry["conflict"]:
            conflicts.append(entry)
        else:
            effective[entry["id"]] = entry["record"]
    return {"agent_id": identity["agent_id"], "canonical_revision": canonical["revision"],
            "local_revision": state(root)[2]["revision"],
            "records": [r for r in effective.values() if r["status"] != "retired"],
            "conflicts": conflicts}


def due(root, now=None):
    identity, canonical, observed = observations(root)
    sent = {fingerprint for item in identity["submissions"] for fingerprint in item["fingerprints"]}
    pending = [entry for entry in observed if digest(entry) not in sent]
    current_week = week(now)
    submitted_this_week = any(item["week"] == current_week for item in identity["submissions"])
    return {"week": current_week, "agent_id": identity["agent_id"],
            "due": bool(pending) and not submitted_this_week,
            "review_due": not submitted_this_week,
            "pending_count": len(pending), "submitted_this_week": submitted_this_week,
            "reason": "already-submitted" if submitted_this_week else ("new-evidence" if pending else "no-new-evidence"),
            "pending": pending, "canonical_hash": digest(canonical["records"])}


def privacy_check(value):
    text = json.dumps(value, ensure_ascii=False)
    patterns = {
        "credential": r"(?i)\b(?:gh[pousr]_[a-z0-9]{16,}|github_pat_[a-z0-9_]{16,}|sk-[a-z0-9_-]{16,})\b",
        "email-address": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "ipv4-address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "local-path": r"(?i)\b[A-Z]:[\\/]",
        "phone-number": r"(?<!\d)(?:\+86[- ]?)?1[3-9]\d{9}(?!\d)",
        "private-key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    }
    for label, pattern in patterns.items():
        storage.require(re.search(pattern, text) is None,
                        f"Outgoing evidence blocked by {label} check; redact locally")


def validate_proposal(bundle):
    version = bundle.get("schema_version")
    fields = {"schema_version", "repository", "week", "agent_id", "platform",
              "baseline_version", "canonical_hash", "observations"}
    storage.require(set(bundle) == fields | ({"review"} if version == 2 else set()),
                    "Unexpected proposal fields")
    storage.require(version in (1, 2), "Invalid proposal schema")
    repository_name(bundle["repository"])
    storage.require(re.fullmatch(r"\d{4}-W\d{2}", bundle["week"]) is not None, "Invalid proposal week")
    datetime.fromisocalendar(int(bundle["week"][:4]), int(bundle["week"][-2:]), 1)
    storage.require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,50}", bundle["agent_id"]) is not None,
                    "Invalid proposal agent")
    storage.require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", bundle["platform"]) is not None,
                    "Invalid platform label")
    storage.require(re.fullmatch(r"[a-f0-9]{64}", bundle["canonical_hash"]) is not None,
                    "Invalid canonical hash")
    storage.require(re.fullmatch(r"\d+\.\d+\.\d+", bundle["baseline_version"]) is not None,
                    "Invalid baseline version")
    storage.require(isinstance(bundle["observations"], list), "Invalid observations")
    if version == 1:
        storage.require(bool(bundle["observations"]), "Empty proposal")
    else:
        review = weekly_review.validate(bundle["review"])
        storage.require(bool(review["activities"]) and bool(review["evidence"]), "Empty weekly review")
        storage.require(bundle["week"] == week(weekly_review.timestamp(review["period_end"])), "Review week mismatch")
        storage.require(set(review["profile_evidence"]) == {e["id"] for e in bundle["observations"]},
                        "Profile changes need current review evidence")
    seen = set()
    for entry in bundle["observations"]:
        storage.require(entry["id"] not in seen, "Duplicate proposal record")
        seen.add(entry["id"])
        storage.require(type(entry["conflict"]) is bool, "Invalid conflict marker")
        storage.require(entry["base_record_hash"] is None or
                        re.fullmatch(r"[a-f0-9]{64}", entry["base_record_hash"]) is not None,
                        "Invalid baseline hash")
        if entry["operation"] == "upsert":
            storage.require(set(entry) == {"operation", "id", "record", "base_record_hash", "conflict"},
                            "Unexpected upsert fields")
            storage.validate_records([entry["record"]])
            storage.require(entry["id"] == entry["record"]["id"], "Record id mismatch")
        else:
            storage.require(entry["operation"] == "delete" and
                            set(entry) == {"operation", "id", "base_record_hash", "conflict"},
                            "Unexpected delete fields")
            storage.require(re.fullmatch(r"[a-z][a-z0-9-]{0,63}", entry["id"]) is not None,
                            "Invalid delete id")
    privacy_check(bundle)
    return bundle


def review_plan(root, now=None):
    report = due(root, now)
    return {"review_due": report["review_due"], "week": report["week"],
            "agent_id": report["agent_id"], **weekly_review.window(now),
            "scope": "Only this host AI's authorized user history; do not collect before the trigger",
            "submitted_this_week": report["submitted_this_week"]}


def prepare(root, now=None, immediate=False, review=None):
    report = due(root, now)
    if report["submitted_this_week"]:
        # --now does not bypass per-week duplicate protection.
        return {k: v for k, v in report.items() if k != "pending"}
    storage.require(review is not None, "A trigger-time weekly review is required; use prepare --review")
    weekly_review.validate(review)
    privacy_check(review)
    end = weekly_review.timestamp(review["period_end"])
    elapsed = (now or datetime.now(timezone.utc)) - end
    storage.require(0 <= elapsed.total_seconds() <= 86400, "Review must come from the current trigger (within 24 hours)")
    if review["coverage"]["status"] == "unavailable":
        return {"prepared": False, "reason": "history-unavailable", "needs_attention": True}
    if not review["activities"] or not review["evidence"]:
        return {"prepared": False, "reason": "no-observed-activity",
                "needs_attention": review["coverage"]["status"] == "partial"}
    pending_by_id = {entry["id"]: entry for entry in report["pending"]}
    storage.require(set(review["profile_evidence"]) <= set(pending_by_id), "Review references a non-pending profile change")
    selected = [pending_by_id[rid] for rid in review["profile_evidence"]]
    settings = config(root)
    identity = state(root)[0]
    bundle = validate_proposal({"schema_version": 2, "repository": settings["repository"],
              "week": report["week"], "agent_id": identity["agent_id"],
              "platform": identity["platform"], "baseline_version": settings["version"],
              "canonical_hash": report["canonical_hash"], "observations": selected, "review": review})
    # Include content hash in local filename. Prepared evidence remains immutable while new work happens.
    outbox = root / ".local" / "outbox"
    outbox.mkdir(exist_ok=True)
    stem = report["week"] + "-" + digest(bundle)[:12]
    path = outbox / (stem + ".json")
    storage.atomic_write(path, bundle)
    branch = f"me/{identity['agent_id']}/{report['week']}"
    remote_path = f"proposals/{report['week']}/{identity['agent_id']}.json"
    title = f"[{report['week']}] {identity['platform']}：本周使用与习惯复盘"
    details = "\n".join(f"- `{e['id']}`：{e['operation']}；上游冲突：{'有' if e['conflict'] else '无'}"
                         for e in bundle["observations"])
    body = (f"定时触发后回顾最近 7 天的使用情况，提出 {len(bundle['observations'])} 条去敏画像建议，供用户统一审核。"
            "本 PR 不修改统一画像或执行规则，不自动合并。\n\n"
            f"来源：{identity['platform']} / `{identity['agent_id']}`\n"
            f"基线版本：{settings['version']}\n\n{weekly_review.render(review)}\n\n"
            f"### 画像改进建议\n{details or '无新增画像修改；保留有证据的本周使用汇总。'}\n\n"
            "验证：提案结构、用户证据类型和基础敏感模式检查通过；真实引文及语义去敏仍由提交代理审查。\n\n"
            "审核事项：确认适用范围、证据、冲突和是否采纳。采纳后通过维护 PR 更新统一画像与版本。\n")
    body_path = outbox / (stem + ".md")
    body_path.write_text(body, encoding="utf-8")
    return {"prepared": True, "bundle": str(path), "body_file": str(body_path), "title": title,
            "repository": settings["repository"], "base": "main", "head": branch,
            "remote_path": remote_path, "fingerprint": digest(bundle)}


def acknowledge(root, bundle_path, pr_url):
    settings = config(root)
    pattern = r"https://github\.com/" + re.escape(settings["repository"]) + r"/pull/[1-9]\d*"
    storage.require(re.fullmatch(pattern, pr_url) is not None, "PR URL must target the configured repository")
    bundle = validate_proposal(storage.read_json(bundle_path))
    storage.require(bundle["repository"] == settings["repository"], "Proposal repository differs from local configuration")
    local = root / ".local"
    identity = storage.read_json(local / "agent.json")
    storage.require(bundle["agent_id"] == identity["agent_id"], "Bundle belongs to another installation")
    entry = {"week": bundle["week"], "url": pr_url,
             "fingerprints": [digest(item) for item in bundle["observations"]]}
    if bundle["schema_version"] == 2:
        entry["review_hash"] = digest(bundle["review"])
    existing = [s for s in identity["submissions"] if s["week"] == entry["week"]]
    if existing:
        storage.require(existing[0] == entry, "Week already acknowledged with different content")
        return {"acknowledged": True, "unchanged": True, "url": pr_url}
    identity["submissions"].append(entry)
    storage.atomic_write(local / "agent.json", identity)
    return {"acknowledged": True, "url": pr_url}


def forget(root, ids, expected, write):
    identity, baseline, local, canonical = state(root)
    original = {r["id"]: r for r in baseline["records"]}
    original.update({r["id"]: r for r in canonical["records"]})
    result = storage.mutate(root / ".local" / "profile.json", "forget", expected, write, ids=ids)
    if write:
        for rid in ids:
            if rid in original:
                identity["deletions"][rid] = digest(original[rid])
        baseline["records"] = [r for r in baseline["records"] if r["id"] not in ids]
        for snapshot in baseline["history"]:
            snapshot["records"] = [r for r in snapshot["records"] if r["id"] not in ids]
        storage.atomic_write(root / ".local" / "baseline.json", baseline)
        storage.atomic_write(root / ".local" / "agent.json", identity)
    result["remote_erased"] = False
    result["note"] = "Canonical GitHub data and prior exports require separate reviewed removal"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--platform", default="generic")
    commands.add_parser("view")
    commands.add_parser("due")
    commands.add_parser("review-plan")
    commands.add_parser("validate")
    change = commands.add_parser("apply")
    change.add_argument("--patch", required=True, type=Path)
    change.add_argument("--write", action="store_true")
    prep = commands.add_parser("prepare")
    prep.add_argument("--review", required=True, type=Path)
    prep.add_argument("--now", action="store_true")
    ack = commands.add_parser("acknowledge")
    ack.add_argument("--bundle", required=True, type=Path)
    ack.add_argument("--pr-url", required=True)
    forget_cmd = commands.add_parser("forget")
    forget_cmd.add_argument("--id", action="append", dest="ids", required=True)
    forget_cmd.add_argument("--expected", required=True, type=int)
    forget_cmd.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    config(root)
    workflow_lock = None
    try:
        if args.command != "init":
            storage.require((root / ".local" / "agent.json").exists(), "Run init first")
            workflow_lock = root / ".local" / "workflow.lock"
            try:
                fd = os.open(workflow_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                workflow_lock = None
                raise ValueError("Another local workflow is running; do not overwrite its state") from None
            os.close(fd)
        if args.command == "init":
            result = init(root, args.platform)
        elif args.command == "view":
            result = view(root)
        elif args.command == "due":
            result = {k: v for k, v in due(root).items() if k != "pending"}
        elif args.command == "review-plan":
            result = review_plan(root)
        elif args.command == "prepare":
            result = prepare(root, immediate=args.now, review=storage.read_json(args.review))
        elif args.command == "acknowledge":
            result = acknowledge(root, args.bundle, args.pr_url)
        elif args.command == "forget":
            result = forget(root, args.ids, args.expected, args.write)
        elif args.command == "validate":
            identity, baseline, local, canonical = state(root)
            result = {"valid": True, "local_revision": local["revision"], "canonical_revision": canonical["revision"]}
        else:
            payload = storage.read_json(args.patch)
            result = storage.mutate(root / ".local" / "profile.json", "apply",
                                    payload["expected_revision"], args.write, patch=payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(f"Me operation failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    finally:
        if workflow_lock is not None:
            workflow_lock.unlink()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
