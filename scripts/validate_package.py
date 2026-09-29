"""Validate an empty public template or a configured personal package."""
import argparse
import json
from pathlib import Path
import re
import sys
import me
import profile_store as storage

ROOT = Path(__file__).resolve().parents[1]


def validate(root=ROOT, template=False):
    settings = me.config(root, allow_unconfigured=True)
    entry = (root / "SKILL.md").read_text(encoding="utf-8")
    storage.require(re.match(r"---\nname: me-skill\ndescription: .+\n---", entry) is not None,
                    "Invalid Skill entrypoint")
    for path in [root / "SKILL.md", root / "README.md", *(root / "references").glob("*.md")]:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" not in target and not target.startswith("#"):
                storage.require((path.parent / target.split('#')[0]).is_file(), "Broken documentation link")
    profile = storage.validate(storage.read_json(root / "references" / "profile.json"))
    me.privacy_check(profile)
    for proposal in (root / "proposals").glob("*/*.json"):
        bundle = me.validate_proposal(storage.read_json(proposal))
        storage.require(bundle["repository"] == settings["repository"], "Proposal points outside owner repository")
    metadata = (root / "agents" / "openai.yaml").read_text(encoding="utf-8")
    storage.require("$me-skill" in metadata and "allow_implicit_invocation: true" in metadata,
                    "Invalid invocation metadata")
    if template:
        storage.require(settings["repository"] is None and settings["display_name"] is None and settings["timezone"] is None,
                        "Public template must not be configured for a person")
        storage.require(not profile["records"] and not profile["history"] and profile["revision"] == 0,
                        "Public template must contain an empty profile")
        storage.require(not (root / ".local").exists() and not (root / "proposals").exists(),
                        "Personal state or proposals must not enter the public template")
    return {"valid": True, "version": settings["version"], "empty_template": settings["repository"] is None,
            "profile_records": len(profile["records"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(validate(template=args.template)))
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(f"Package validation failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
