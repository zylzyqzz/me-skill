"""Versioned local profile storage. No network, model API, or third-party dependencies."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import date, datetime, timezone

DEFAULT_STORE = Path(__file__).resolve().parents[1] / "references" / "profile.json"
STATUSES = {"confirmed", "candidate", "historical", "retired"}
KINDS = {"direct_user", "historical_user", "user_document", "inference"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value, label, limit=2000):
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= limit,
            f"Invalid {label}")


def validate_records(records):
    require(isinstance(records, list), "records must be a list")
    seen = set()
    fields = {"id", "topic", "statement", "use", "scope", "status", "reviewed_on", "evidence"}
    for rec in records:
        require(isinstance(rec, dict) and set(rec) == fields, "Invalid record fields")
        for key in fields - {"evidence"}:
            nonempty(rec[key], key)
        rid = rec["id"]
        require(re.fullmatch(r"[a-z][a-z0-9-]{0,63}", rid) is not None, "Invalid record id")
        require(rid not in seen, "Duplicate record id")
        seen.add(rid)
        require(rec["status"] in STATUSES, "Invalid status")
        require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", rec["reviewed_on"]) is not None,
                "reviewed_on must be YYYY-MM-DD")
        date.fromisoformat(rec["reviewed_on"])
        evidence = rec["evidence"]
        require(isinstance(evidence, list) and 1 <= len(evidence) <= 20, "Evidence required")
        for item in evidence:
            require(isinstance(item, dict) and set(item) == {"kind", "reference", "summary"},
                    "Invalid evidence fields")
            require(item["kind"] in KINDS, "Invalid evidence kind")
            nonempty(item["reference"], "evidence reference")
            nonempty(item["summary"], "evidence summary")
        if rec["status"] == "confirmed":
            direct = any(e["kind"] == "direct_user" for e in evidence)
            historical = {e["reference"] for e in evidence if e["kind"] == "historical_user"}
            require(direct or len(historical) >= 2,
                    "confirmed requires direct user evidence or two independent user references")


def validate(store):
    fields = {"schema_version", "revision", "updated_at", "records", "history", "last_change"}
    require(isinstance(store, dict) and set(store) == fields, "Invalid store fields")
    require(type(store["schema_version"]) is int and store["schema_version"] == 1,
            "Unsupported schema")
    require(type(store["revision"]) is int and store["revision"] >= 0, "Invalid revision")
    nonempty(store["updated_at"], "updated_at")
    validate_records(store["records"])
    require(isinstance(store["history"], list), "Invalid history")
    previous = -1
    for snap in store["history"]:
        require(isinstance(snap, dict) and set(snap) == {"revision", "updated_at", "records"},
                "Invalid snapshot")
        rev = snap["revision"]
        require(type(rev) is int and previous < rev < store["revision"], "Invalid snapshot revision")
        nonempty(snap["updated_at"], "snapshot updated_at")
        validate_records(snap["records"])
        previous = rev
    change = store["last_change"]
    require(isinstance(change, dict) and set(change) == {"operation", "ids", "reason"},
            "Invalid last_change")
    require(change["operation"] in {"seed", "apply", "rollback", "forget"}, "Invalid operation")
    require(isinstance(change["ids"], list) and all(isinstance(x, str) for x in change["ids"]),
            "Invalid changed ids")
    nonempty(change["reason"], "change reason")
    return store


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def evolve(store, operation, expected, patch=None, target=None, ids=None):
    validate(store)
    require(type(expected) is int and store["revision"] == expected,
            "Revision conflict: reread and merge; no changes written")
    result = copy.deepcopy(store)
    before = copy.deepcopy(store["records"])
    if operation == "apply":
        require(isinstance(patch, dict) and set(patch) == {"expected_revision", "reason", "upsert"},
                "Invalid patch fields")
        nonempty(patch["reason"], "patch reason")
        validate_records(patch["upsert"])
        require(bool(patch["upsert"]), "Empty patch")
        mapped = {rec["id"]: rec for rec in result["records"]}
        changed = [rec["id"] for rec in patch["upsert"] if mapped.get(rec["id"]) != rec]
        require(bool(changed), "No new evidence or changes; no revision created")
        mapped.update({rec["id"]: copy.deepcopy(rec) for rec in patch["upsert"]})
        result["records"] = list(mapped.values())
        reason = patch["reason"]
    elif operation == "rollback":
        snapshots = [snap for snap in result["history"] if snap["revision"] == target]
        require(len(snapshots) == 1, "Target revision not in history")
        result["records"] = copy.deepcopy(snapshots[0]["records"])
        require(result["records"] != before, "Target content already active")
        old = {r["id"]: r for r in before}
        new = {r["id"]: r for r in result["records"]}
        changed = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
        reason = f"Restore revision {target} as a new revision"
    elif operation == "forget":
        require(isinstance(ids, list) and ids and all(isinstance(x, str) for x in ids),
                "At least one id required")
        wanted = set(ids)
        known = {r["id"] for r in before}
        for snap in result["history"]:
            known.update(r["id"] for r in snap["records"])
        require(wanted <= known, "Unknown forget id")
        before = [r for r in before if r["id"] not in wanted]
        result["records"] = copy.deepcopy(before)
        for snap in result["history"]:
            snap["records"] = [r for r in snap["records"] if r["id"] not in wanted]
        changed = sorted(wanted)
        reason = "Remove selected records from current state and all internal snapshots"
    else:
        raise ValueError("Unknown operation")
    result["history"].append({"revision": store["revision"],
                              "updated_at": store["updated_at"], "records": before})
    result["revision"] += 1
    result["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result["last_change"] = {"operation": operation, "ids": changed, "reason": reason}
    return validate(result)


def atomic_write(path, data):
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".profile-", suffix=".tmp",
                                         delete=False) as stream:
            temp = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def mutate(path, operation, expected, write=False, **kwargs):
    path = Path(path).resolve(strict=True)
    # Even preview acquires a short lock so cooperating writers cannot race its read.
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ValueError("Profile is locked; check the other writer before retrying") from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        current = validate(read_json(path))
        updated = evolve(current, operation, expected, **kwargs)
        if write:
            atomic_write(path, updated)
            validate(read_json(path))
        return {"written": write, "from_revision": current["revision"],
                "to_revision": updated["revision"], "change": updated["last_change"]}
    finally:
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show")
    show.add_argument("--all", action="store_true", dest="all_records")
    commands.add_parser("validate")
    apply = commands.add_parser("apply")
    apply.add_argument("--patch", required=True, type=Path)
    rollback = commands.add_parser("rollback")
    rollback.add_argument("--target", type=int, required=True)
    rollback.add_argument("--expected", type=int, required=True)
    forget = commands.add_parser("forget")
    forget.add_argument("--id", action="append", required=True, dest="ids")
    forget.add_argument("--expected", type=int, required=True)
    for cmd in (apply, rollback, forget):
        cmd.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command in {"show", "validate"}:
            store = validate(read_json(args.store))
            output = {"valid": True, "revision": store["revision"],
                      "record_count": len(store["records"])}
            if args.command == "show":
                output["records"] = [r for r in store["records"]
                                     if args.all_records or r["status"] in {"confirmed", "historical"}]
        elif args.command == "apply":
            patch = read_json(args.patch)
            require(isinstance(patch, dict), "Patch must be an object")
            output = mutate(args.store, "apply", patch.get("expected_revision"),
                            args.write, patch=patch)
        elif args.command == "rollback":
            output = mutate(args.store, "rollback", args.expected, args.write, target=args.target)
        else:
            output = mutate(args.store, "forget", args.expected, args.write, ids=args.ids)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        # Avoid printing payloads, raw JSON, or personal record contents in errors.
        print(f"Profile operation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
