#!/usr/bin/env python3
"""
synchronizer.py
Synchronize local monorepo -> central repo and per-project "vitrine" repos.

Usage:
  python synchronizer.py --config _ark_system/sync_config.json [--dry-run] [--allow-dirty] [--force]

Requirements:
  - git in PATH
  - network auth configured for git pushes (ssh keys or credential helper)
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from tempfile import NamedTemporaryFile

LOCK_FILE = os.path.join(os.getcwd(), ".synchronizer.lock")
DEFAULT_LOCK_TIMEOUT = 2 * 60 * 60  # seconds (2 hours)

def run_cmd(cmd, cwd=None, capture=False, check=True, dry_run=False):
    """Run command, return (returncode, stdout). Raises subprocess.CalledProcessError if check and rc != 0."""
    print(f"> {' '.join(cmd)} (cwd={cwd or os.getcwd()})")
    if dry_run:
        return 0, ""
    if capture:
        proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd, output=proc.stdout)
        return proc.returncode, proc.stdout
    else:
        proc = subprocess.run(cmd, cwd=cwd)
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
        return proc.returncode, None

def ensure_repo_root():
    """Return git top-level path; ensure we are inside a git repo."""
    try:
        rc, out = run_cmd(["git", "rev-parse", "--show-toplevel"], capture=True)
        top = out.strip()
        return top
    except Exception as e:
        print("Error: current directory is not inside a git repository or git is missing.", file=sys.stderr)
        raise

def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_lock(timeout_seconds):
    if os.path.exists(LOCK_FILE):
        # check age
        age = time.time() - os.path.getmtime(LOCK_FILE)
        if age < timeout_seconds:
            raise RuntimeError(f"Lock file exists and is recent (age {age:.0f}s). Abort.")
        else:
            print("Stale lock found: removing.")
            os.remove(LOCK_FILE)
    with open(LOCK_FILE, "w", encoding="utf-8") as lf:
        lf.write(f"{os.getpid()}\n")
        lf.write(datetime.utcnow().isoformat() + "\n")

def remove_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception as e:
        print(f"Warning: failed to remove lock file: {e}")

def ensure_clean_worktree(allow_dirty):
    # Check for uncommitted changes
    rc, stdout = run_cmd(["git", "status", "--porcelain"], capture=True)
    if stdout.strip():
        if allow_dirty:
            print("Warning: working tree is dirty but --allow-dirty specified; continuing.")
        else:
            raise RuntimeError("Working tree has uncommitted changes. Commit or pass --allow-dirty.")

def ensure_remote_exists(remote_name, remote_url, dry_run):
    # if remote exists and url matches -> ok; if exists but url differs -> create temp remote name
    rc, out = run_cmd(["git", "remote", "get-url", remote_name], capture=True, check=False, dry_run=dry_run)
    if rc == 0 and out.strip():
        existing = out.strip()
        if existing == remote_url:
            return remote_name, False  # no cleanup needed
        # remote exists but different URL, create temp remote
    # create remote
    temp_name = f"temp_remote_{int(time.time())}"
    run_cmd(["git", "remote", "add", temp_name, remote_url], dry_run=dry_run)
    return temp_name, True

def remove_remote_if_temp(remote_name, was_temp, dry_run):
    if was_temp:
        run_cmd(["git", "remote", "remove", remote_name], dry_run=dry_run)

def push_central(central_remote, central_branch, dry_run, force):
    # Push local HEAD (or branch) to central remote
    ref = central_branch or "HEAD"
    args = ["git", "push", central_remote, f"HEAD:{ref}"]
    if force:
        args.insert(2, "--force")
    run_cmd(args, dry_run=dry_run)

def subtree_push(prefix, remote_name, remote_branch, dry_run, force):
    """
    Try 'git subtree push --prefix=prefix remote_name remote_branch'.
    If fails (nonzero), fallback to split->push->delete-temp-branch approach.
    """
    try:
        args = ["git", "subtree", "push", "--prefix", prefix, remote_name, remote_branch]
        if force:
            # subtree push doesn't accept --force widely; fallback will use --force
            pass
        run_cmd(args, dry_run=dry_run)
        return
    except subprocess.CalledProcessError as e:
        print(f"git subtree push failed or not available: {e}. Using fallback (subtree split).")

    # Fallback: create a split branch, force-push it, then delete
    temp_branch = f"subtree-split-{int(time.time())}"
    run_cmd(["git", "subtree", "split", "--prefix", prefix, "-b", temp_branch], dry_run=dry_run)
    push_args = ["git", "push", remote_name, f"{temp_branch}:{remote_branch}"]
    if force:
        push_args.insert(2, "--force")
    run_cmd(push_args, dry_run=dry_run)
    # delete temp branch locally
    run_cmd(["git", "branch", "-D", temp_branch], dry_run=dry_run)

def main():
    parser = argparse.ArgumentParser(description="Synchronize monorepo to central and project remotes (subtrees).")
    parser.add_argument("--config", "-c", default="_ark_system/sync_config.json", help="Path to sync config JSON")
    parser.add_argument("--dry-run", action="store_true", help="Show commands but don't execute")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow uncommitted changes")
    parser.add_argument("--force", action="store_true", help="Force pushes to remote (use with care)")
    parser.add_argument("--lock-timeout", type=int, default=DEFAULT_LOCK_TIMEOUT, help="Lock timeout seconds before stale")
    args = parser.parse_args()

    # ensure git repo
    try:
        repo_root = ensure_repo_root()
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    os.chdir(repo_root)

    # load config
    try:
        cfg = load_config(args.config)
    except Exception as e:
        print(f"Failed to load config {args.config}: {e}", file=sys.stderr)
        sys.exit(1)

    central = cfg.get("central", {})
    central_remote = central.get("remote", "origin")
    central_branch = central.get("branch", "main")

    projects = cfg.get("projects", [])

    # Acquire lock
    try:
        write_lock(args.lock_timeout)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    try:
        # Working tree check
        ensure_clean_worktree(args.allow_dirty)

        # 1) Push central
        print(f"\n==> Pushing central repo to '{central_remote}/{central_branch}'")
        push_central(central_remote, central_branch, args.dry_run, args.force)

        # 2) For each project: subtree push
        for p in projects:
            prefix = p["prefix"]
            repo_url = p["repo_url"]
            branch = p.get("branch", "main")
            print(f"\n==> Project '{p.get('name', prefix)}' -> prefix '{prefix}' -> {repo_url}:{branch}")

            # ensure remote exists (or add temporary)
            temp_remote_name = None
            was_temp = False
            # Prefer using a named remote if provided in config
            remote_name = p.get("remote_name")
            if remote_name:
                try:
                    # try to use existing remote if name present
                    run_cmd(["git", "remote", "get-url", remote_name], dry_run=args.dry_run)
                except Exception:
                    # if doesn't exist, create it
                    run_cmd(["git", "remote", "add", remote_name, repo_url], dry_run=args.dry_run)
                    was_temp = True
                    temp_remote_name = remote_name
            else:
                temp_remote_name, was_temp = ensure_remote_exists("temp_sync_remote", repo_url, args.dry_run)

            try:
                subtree_push(prefix, temp_remote_name or remote_name, branch, args.dry_run, args.force)
            finally:
                if was_temp:
                    remove_remote_if_temp(temp_remote_name or remote_name, was_temp, args.dry_run)

        print("\nAll operations completed successfully.")
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        remove_lock()
        sys.exit(2)
    finally:
        remove_lock()

if __name__ == "__main__":
    import argparse
    main()
