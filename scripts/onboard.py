"""Install a self-contained user profile into a verified host instruction file.

The caller must discover the host's real persistent instruction entry point.
Dry-run by default; never edits a platform-managed memory store.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import profile_store as storage
import me

BEGIN = "<!-- me-skill:begin -->"
END = "<!-- me-skill:end -->"


def render(root):
    settings = me.config(root)
    profile = me.view(root)
    storage.require(any(r["status"] == "confirmed" for r in profile["records"]),
                    "Blank template: collect this user's confirmed preferences before onboarding")
    lines = [BEGIN, f"# {settings['display_name']} 的常驻协作画像", f"来源版本：me-skill {settings['version']}；画像修订 {profile['canonical_revision']}。",
             "这段是该 AI 宿主的用户级全局个人上下文，适用于所有项目和新对话。日常直接应用，不要求用户再次调用 Skill，也无需每轮重新读 Skill。",
             "两项独立任务：周一触发后回顾最近 7 天并提 PR；周五检查指定仓库 main，有更新自动验证、升级和刷新此全局画像。",
             "全局默认不等于实时共享全部聊天；其他对话的新信息需要宿主记忆或用户审核后的画像同步。",
             "当前用户明确指令优先；遵守平台权限与项目规则。画像不是对所有任务的预授权。",
             "理解范围仅限已提供并有来源的资料；不声称知道用户全部隐私、全部项目现状或其他 AI 的记录。",
             "平时不为周报扫描、采集或沉淀聊天；仅定时任务触发或用户明确要求复盘时回顾最近 7 天。",
             "用户当下纠正立即用于当前任务；只有明确要求记住/修改画像时才即时持久化。",
             "维护、升级、遗忘和每周复盘时再读安装目录里的对应流程；普通开发无需重新加载。", ""]
    labels = {"confirmed": "已确认的协作默认值", "historical": "有范围的历史背景（当前状态需核验）",
              "candidate": "待核实背景（不是已确认事实，不作硬约束）"}
    for status, title in labels.items():
        lines += ["## " + title]
        for record in profile["records"]:
            if record["status"] == status:
                lines.append(f"- {record['topic']} [{record['scope']}]：{record['statement']} {record['use']}")
        lines.append("")
    lines += ["## 背景说明", (root / "references" / "context.md").read_text(encoding="utf-8"), END]
    result = "\n".join(lines)
    me.privacy_check(result)
    storage.require(BEGIN not in result[len(BEGIN):] and result.count(END) == 1,
                    "Profile contains reserved instruction markers")
    return result


def merge(original, block):
    text = original.decode("utf-8")
    storage.require(text.count(BEGIN) == text.count(END) and text.count(BEGIN) <= 1,
                    "Malformed or duplicate Me instruction blocks; inspect before modifying")
    if BEGIN in text:
        start, end = text.index(BEGIN), text.index(END)
        storage.require(start < end, "Malformed instruction block order")
        text = text[:start] + block + text[end + len(END):]
    else:
        text += ("\n\n" if text else "") + block + "\n"
    return text.encode("utf-8")


def install(root, target, write=False):
    target = Path(target)
    storage.require(target.is_absolute() and target.suffix.lower() == ".md",
                    "Supply the verified absolute Markdown instruction path")
    storage.require(not target.is_symlink() and target.parent.is_dir(), "Invalid instruction target")
    storage.require(not target.resolve().is_relative_to(root.resolve()),
                    "Persistent host instructions must live outside the Skill package")
    storage.require((root / ".local" / "agent.json").exists(), "Run me.py init first")
    block = render(root)
    original = target.read_bytes() if target.exists() else b""
    updated = merge(original, block)
    # Leave room for repository rules under common host context limits.
    storage.require(len(updated) <= 24576, "Instructions exceed 24 KiB; adapt to host limits before installing")
    result = {"target": str(target), "changed": updated != original, "written": False,
              "bytes": len(updated), "new_session_verified": False}
    if not write:
        return result
    lock = target.with_name(target.name + ".me.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("Instruction writer active; inspect before retrying") from None
    os.close(fd)
    temp_path = None
    try:
        storage.require((target.read_bytes() if target.exists() else b"") == original,
                        "Instructions changed concurrently; reread before writing")
        if updated != original:
            if target.exists():
                backups = root / ".local" / "instruction-backups"
                backups.mkdir(exist_ok=True)
                backup = backups / (hashlib.sha256(original).hexdigest() + ".md")
                if not backup.exists():
                    backup.write_bytes(original)
                result["backup"] = str(backup)
            fd, name = tempfile.mkstemp(prefix=".me-", suffix=".tmp", dir=target.parent)
            temp_path = Path(name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            if target.exists():
                os.chmod(temp_path, target.stat().st_mode)
            os.replace(temp_path, target)
        storage.require(target.read_bytes() == updated, "Instruction readback failed")
        (root / ".local" / "assistant-context.md").write_text(block + "\n", encoding="utf-8")
        storage.atomic_write(root / ".local" / "onboarding.json", {
            "version": me.config(root)["version"], "instruction_path": str(target),
            "block_sha256": hashlib.sha256(block.encode("utf-8")).hexdigest(),
            "file_verified": True, "new_session_verified": False})
        result["written"] = True
        return result
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        lock.unlink()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=me.ROOT)
    parser.add_argument("--instructions", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.root.resolve(), args.instructions, args.write), ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(f"Onboarding failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
