"""Submit a reviewed, sanitized proposal using existing standard GitHub authentication."""
import argparse
import base64
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import me
import profile_store as storage



@lru_cache(maxsize=1)
def credential():
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    if shutil.which("gh"):
        result = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"],
                                text=True, capture_output=True, timeout=20)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    if shutil.which("git"):
        env = dict(os.environ, GCM_INTERACTIVE="Never", GIT_TERMINAL_PROMPT="0")
        result = subprocess.run(["git", "credential", "fill"],
                                input="protocol=https\nhost=github.com\n\n",
                                text=True, capture_output=True, env=env, timeout=20)
        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if result.returncode == 0 and values.get("password"):
            return values["password"]
    raise ValueError("No existing GitHub authentication; sign in on this host, never paste tokens into chat")


def api(path, method="GET", data=None, missing_ok=False, *, repository):
    PREFIX = "/repos/" + me.repository_name(repository)
    storage.require(path == PREFIX or path.startswith(PREFIX + "/"), "API destination outside configured repository")
    request = Request("https://api.github.com" + path, method=method,
                      data=None if data is None else json.dumps(data).encode("utf-8"),
                      headers={"Authorization": "Bearer " + credential(),
                               "Accept": "application/vnd.github+json", "Content-Type": "application/json",
                               "User-Agent": "me-skill", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urlopen(request, timeout=45) as response:
            content = response.read()
        return json.loads(content) if content else {}
    except HTTPError as error:
        if error.code == 404 and missing_ok:
            return None
        raise ValueError(f"GitHub API HTTP {error.code}; credentials and response body suppressed") from None


def submit_unlocked(root, bundle_path, write=False):
    REPO = me.config(root)["repository"]
    PREFIX = "/repos/" + REPO
    def request(path, method="GET", data=None, missing_ok=False):
        return api(path, method, data, missing_ok, repository=REPO)
    bundle = me.validate_proposal(storage.read_json(bundle_path))
    storage.require(bundle["schema_version"] == 2, "New submissions require a trigger-time weekly review")
    storage.require(bundle["repository"] == REPO, "Proposal repository differs from local configuration")
    identity = me.state(root)[0]
    storage.require(bundle["agent_id"] == identity["agent_id"], "Bundle belongs to another installation")
    fingerprints = [me.digest(item) for item in bundle["observations"]]
    for item in identity["submissions"]:
        if item["week"] == bundle["week"]:
            storage.require(item["fingerprints"] == fingerprints and
                            item.get("review_hash") == me.digest(bundle["review"]),
                            "This installation already submitted different evidence this week")
    body_path = Path(bundle_path).with_suffix(".md")
    body = body_path.read_text(encoding="utf-8")
    me.privacy_check(body)
    repo = request(PREFIX)
    storage.require(repo["full_name"] == REPO and repo["private"], "Repository must remain private")
    storage.require(repo.get("permissions", {}).get("push", False), "GitHub write permission required")
    branch = f"me/{bundle['agent_id']}/{bundle['week']}"
    path = f"proposals/{bundle['week']}/{bundle['agent_id']}.json"
    query = urlencode({"state": "all", "head": REPO.split("/")[0] + ":" + branch, "base": "main", "per_page": 100})
    prs = request(PREFIX + "/pulls?" + query)
    storage.require(len(prs) <= 1, "Multiple PRs found for the same installation/week; review manually")
    if prs and prs[0]["state"] != "open":
        raise ValueError("This week's PR is already closed or merged; reconcile its receipt before retrying")
    ref_path = PREFIX + "/git/ref/heads/" + quote(branch, safe="/")
    ref = request(ref_path, missing_ok=True)
    if ref:
        comparison = request(PREFIX + "/compare/main..." + quote(branch, safe=""))
        storage.require(all(item["filename"] == path for item in comparison.get("files", [])),
                        "Proposal branch contains unrelated changes; do not overwrite")
    if not write:
        return {"ready": True, "written": False, "repository": REPO, "head": branch,
                "path": path, "existing_pr": prs[0]["html_url"] if prs else None}
    if ref is None:
        main = request(PREFIX + "/git/ref/heads/main")
        request(PREFIX + "/git/refs", "POST", {"ref": "refs/heads/" + branch, "sha": main["object"]["sha"]})
    content_path = PREFIX + "/contents/" + path
    current = request(content_path + "?" + urlencode({"ref": branch}), missing_ok=True)
    content = json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"
    current_content = base64.b64decode(current["content"]).decode("utf-8") if current else None
    if current_content != content:
        payload = {"message": "Add weekly collaboration evidence for " + bundle["week"],
                   "branch": branch, "content": base64.b64encode(content.encode("utf-8")).decode("ascii")}
        if current:
            payload["sha"] = current["sha"]
        request(content_path, "PUT", payload)
    title = f"[{bundle['week']}] {bundle['platform']}：本周使用与习惯复盘"
    if prs:
        pr = request(PREFIX + f"/pulls/{prs[0]['number']}", "PATCH", {"title": title, "body": body})
    else:
        pr = request(PREFIX + "/pulls", "POST", {"title": title, "body": body, "head": branch,
                  "base": "main", "draft": False, "maintainer_can_modify": True})
    verified = request(PREFIX + f"/pulls/{pr['number']}")
    files = request(PREFIX + f"/pulls/{pr['number']}/files?per_page=100")
    remote = request(content_path + "?" + urlencode({"ref": branch}))
    storage.require(verified["base"]["ref"] == "main" and verified["head"]["ref"] == branch,
                    "PR branch verification failed")
    storage.require([f["filename"] for f in files] == [path], "PR file scope verification failed")
    storage.require(base64.b64decode(remote["content"]).decode("utf-8") == content,
                    "Remote proposal content differs")
    receipt = me.acknowledge(root, bundle_path, verified["html_url"])
    return {"submitted": True, "verified": True, "url": verified["html_url"],
            "head_sha": verified["head"]["sha"], "file": path, "receipt": receipt}


def submit(root, bundle_path, write=False):
    lock = root / ".local" / "workflow.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("Another local workflow is running; do not submit concurrently") from None
    os.close(fd)
    try:
        return submit_unlocked(root, bundle_path, write)
    finally:
        lock.unlink()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(submit(me.ROOT, args.bundle, args.write), ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError) as error:
        print(f"Submission failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
