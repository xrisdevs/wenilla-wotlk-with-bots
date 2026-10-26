#!/usr/bin/env python3
"""Restore the pinned server/client source trees and this repo's patches.

Existing trees must be at the pinned revision. Local changes are never reset.
"""
import argparse
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    sources = json.loads((ROOT / "sources.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=["all", *sources], default="all", nargs="?")
    args = parser.parse_args()
    for name, spec in sources.items():
        if args.source not in ("all", name):
            continue
        dest = ROOT / spec["directory"]
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            run("git", "init", str(dest))
            run("git", "-C", str(dest), "remote", "add", "origin", spec["url"])
            run("git", "-C", str(dest), "fetch", "--depth=1", "origin", spec["revision"])
            run("git", "-C", str(dest), "checkout", "--detach", "FETCH_HEAD")
        git = ["git", "-C", str(dest)]
        head = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
        if head != spec["revision"]:
            raise SystemExit(f"{name}: expected {spec['revision']}, found {head}; leaving tree untouched")
        if not spec.get("patch"):
            print(f"{name}: restored {head} (upstream NPCBots)")
            continue
        patch = str(ROOT / spec["patch"])
        applied = subprocess.run([*git, "apply", "--reverse", "--check", patch],
                                 capture_output=True).returncode == 0
        if applied:
            print(f"{name}: patch already applied")
            continue
        run(*git, "apply", "--check", patch)
        run(*git, "apply", patch)
        print(f"{name}: restored {head} with {spec['patch']}")


if __name__ == "__main__":
    main()
