"""Configure an empty template for its current owner; no network or scheduled jobs."""
import argparse
import json
from pathlib import Path
import re
import sys

import me
import profile_store as storage


def configure(root, repository, display_name, timezone, write=False):
    me.repository_name(repository)
    storage.require(repository.lower() != "zylzyqzz/me-skill", "Choose your own private repository, not the public template")
    storage.nonempty(display_name, "display name", 80)
    storage.require(re.fullmatch(r"UTC|[A-Za-z_+-]+(?:/[A-Za-z0-9_+-]+)+", timezone) is not None,
                    "Use a host-verified IANA timezone, for example Asia/Shanghai")
    me.privacy_check({"display_name": display_name})
    settings = me.config(root, allow_unconfigured=True)
    initialized = (root / ".local" / "agent.json").exists()
    storage.require(not initialized or settings["repository"] == repository,
                    "Installation already has an owner repository; migrate explicitly, do not reroute evidence")
    updated = dict(settings, repository=repository, display_name=display_name, timezone=timezone)
    if write and updated != settings:
        storage.atomic_write(root / "me.json", updated)
    return {"configured": write or settings == updated, "written": write and updated != settings,
            "repository": repository, "display_name": display_name, "timezone": timezone,
            "private_repository_verified": False, "schedulers_created": False}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=me.ROOT)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--timezone", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(configure(args.root.resolve(), args.repository, args.display_name,
                                   args.timezone, args.write), ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(f"Configuration failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
