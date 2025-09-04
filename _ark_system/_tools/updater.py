#!/usr/bin/env python3
"""
Universal Updater for apply_modifications.py and other critical tools.

Features:
- Modes: replace | delete | patch
- Atomic writes (temp -> fsync -> os.replace)
- Backup + rotation
- expected_checksum_before verification (clean checksum)
- py_compile syntax check for Python replacements
- Lock file with staleness handling
- Dry-run mode
- Detailed JSON receipt saved to _ark_system/logs/updater_receipts/
- Rollback on failure
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import hashlib
import tempfile
import shutil
import time
import re
import py_compile
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any, List

# ---------- CONFIG ----------
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
TOOLS_DIR = os.path.join(ROOT_DIR, '_ark_system', '_tools')
STAGING_DIR = os.path.join(ROOT_DIR, '_ark_system', '_staging')
BACKUP_DIR = os.path.join(ROOT_DIR, '_ark_system', 'backup')
LOG_DIR = os.path.join(ROOT_DIR, '_ark_system', 'logs')
RECEIPT_DIR = os.path.join(LOG_DIR, 'updater_receipts')
LOCK_FILE = os.path.join(STAGING_DIR, '.updater.lock')
STALE_LOCK_SECONDS = 2 * 60 * 60  # 2 hours
MAX_BACKUPS = 10
CHECKSUM_TAG_RE = re.compile(r"\s*<!--\s*\[ARK_INTEGRITY_CHECKSUM::sha256:[0-9a-fA-F]{64}\]\s*-->\s*$", flags=re.IGNORECASE)
# -----------------------------

os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(RECEIPT_DIR, exist_ok=True)
os.makedirs(STAGING_DIR, exist_ok=True)

# ---------- Utilities ----------

def now_ts() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def calculate_clean_checksum(data: Optional[bytes]) -> str:
    """Compute clean SHA256: decode (utf-8-sig fallback latin-1), strip trailing checksum tag, normalize CRLF->LF."""
    if not data:
        # SHA256 of empty bytes
        return hashlib.sha256(b"").hexdigest()
    try:
        txt = data.decode('utf-8-sig')
    except Exception:
        txt = data.decode('latin-1', errors='replace')
    # remove trailing tag(s)
    txt = re.sub(CHECKSUM_TAG_RE, "", txt)
    txt = txt.replace('\r\n', '\n')
    return hashlib.sha256(txt.encode('utf-8')).hexdigest()

def remove_all_checksum_tags_from_text(txt: str) -> Tuple[str, int]:
    """Remove all occurrences of checksum tag (usually trailing) and return (cleaned_text, count_removed)."""
    cleaned, count = re.subn(r"\s*<!--\s*\[ARK_INTEGRITY_CHECKSUM::sha256:[0-9a-fA-F]{64}\]\s*-->\s*", "\n", txt, flags=re.IGNORECASE)
    # cleanup duplicate trailing newlines
    cleaned = cleaned.rstrip() + ("\n" if cleaned and not cleaned.endswith("\n") else "")
    return cleaned, count

def atomic_write_file(path: str, data: bytes) -> None:
    """Write bytes to path atomically (temp file in same dir -> fsync -> replace)."""
    dirname = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dirname, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

def backup_and_rotate(target_path: str, backup_dir: str = BACKUP_DIR, max_backups: int = MAX_BACKUPS) -> Optional[str]:
    """Copy target_path to backup with timestamp; rotate older backups. Return backup path or None if target missing."""
    if not os.path.exists(target_path):
        return None
    os.makedirs(backup_dir, exist_ok=True)
    base = os.path.basename(target_path)
    ts = now_ts()
    name = f"{base}.{ts}.bak"
    dest = os.path.join(backup_dir, name)
    shutil.copy2(target_path, dest)
    pattern = os.path.join(backup_dir, f"{base}.*.bak")
    files = sorted([p for p in (glob := __import__('glob').glob(pattern))], key=os.path.getmtime)
    while len(files) > max_backups:
        to_remove = files.pop(0)
        try:
            os.remove(to_remove)
        except Exception:
            pass
    return dest

def safe_read(path: str) -> Optional[bytes]:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()

# ---------- Locking ----------

def acquire_lock(logger, stale_seconds: int = STALE_LOCK_SECONDS) -> bool:
    """Acquire lock file. If lock exists and is stale, remove it. Returns True if lock acquired."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r", encoding="utf-8") as lf:
                content = lf.read().strip()
            pid = int(content.split()[0]) if content else None
        except Exception:
            pid = None
        mtime = os.path.getmtime(LOCK_FILE)
        age = time.time() - mtime
        if age > stale_seconds:
            logger.warning(f"Stale lock detected (age {age:.0f}s). Removing lock file.")
            try:
                os.remove(LOCK_FILE)
            except Exception as e:
                logger.error(f"Failed to remove stale lock file: {e}")
                return False
        else:
            logger.critical("Lock file exists and is recent. Another updater may be running. Abort.")
            return False
    try:
        with open(LOCK_FILE, "x", encoding="utf-8") as lf:
            lf.write(f"{os.getpid()} {now_ts()}\n")
        return True
    except FileExistsError:
        logger.critical("Failed to create lock file (race?). Abort.")
        return False

def release_lock(logger):
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            logger.info("Lock file released.")
    except Exception as e:
        logger.error(f"Failed to remove lock file: {e}")

# ---------- Actions: replace / delete / patch ----------

def action_replace(target: str, source: str, expected_before: Optional[str], dry_run: bool, logger, receipt: Dict[str, Any]) -> None:
    """Full replace target with source file (source must exist in staging)."""
    receipt["action"] = "replace"
    if not os.path.exists(source):
        raise FileNotFoundError(f"Source '{source}' not found.")
    new_bytes = safe_read(source)
    if new_bytes is None:
        raise FileNotFoundError(f"Could not read source '{source}'.")
    new_clean = calculate_clean_checksum(new_bytes)

    # verify expected_before if provided
    current_bytes = safe_read(target)
    current_clean = calculate_clean_checksum(current_bytes)
    receipt["before"] = {"exists": bool(current_bytes), "clean_checksum": current_clean}

    if expected_before and current_clean != expected_before:
        raise Exception(f"expected_checksum_before mismatch: expected {expected_before}, found {current_clean}")

    # verify source integrity optionally via provided expected (receipt will store)
    receipt["source"] = {"path": source, "new_clean_checksum": new_clean, "size": len(new_bytes)}

    # optional syntax check if Python target
    if target.endswith(".py"):
        try:
            if not dry_run:
                py_compile.compile(source, doraise=True)
            receipt.setdefault("checks", {})["py_compile_source"] = "ok"
        except Exception as e:
            receipt.setdefault("checks", {})["py_compile_source"] = f"fail: {e}"
            raise

    # backup
    backup = None
    if os.path.exists(target):
        backup = backup_and_rotate(target)
        receipt["backup"] = backup

    # write (atomic)
    if dry_run:
        logger.info(f"DRY-RUN: would replace {target} with {source}")
        receipt["status"] = "DRY_RUN"
        return

    # perform atomic replacement
    atomic_write_file(target, new_bytes)
    logger.info(f"Replaced '{target}' with '{source}' (atomic).")

    # post-verify (read back clean checksum)
    written = safe_read(target)
    written_clean = calculate_clean_checksum(written)
    receipt["after"] = {"clean_checksum": written_clean, "size": len(written) if written else 0}
    if written_clean != new_clean:
        # attempt rollback
        if backup:
            shutil.copy2(backup, target)
            logger.error("Post-verify mismatch — rolled back from backup.")
        raise Exception(f"POST-WRITE verification failed: expected {new_clean}, found {written_clean}")

    # syntax check for python target (after replacement)
    if target.endswith(".py"):
        try:
            py_compile.compile(target, doraise=True)
            receipt.setdefault("checks", {})["py_compile_target"] = "ok"
        except Exception as e:
            # rollback
            if backup:
                shutil.copy2(backup, target)
                logger.error("Post-py-compile fail — rolled back from backup.")
            raise

    receipt["status"] = "SUCCESS"

def action_delete(target: str, expected_before: Optional[str], dry_run: bool, logger, receipt: Dict[str, Any]) -> None:
    receipt["action"] = "delete"
    current_bytes = safe_read(target)
    if not current_bytes:
        receipt["status"] = "NO_OP"
        logger.info(f"Target '{target}' does not exist; nothing to delete.")
        return
    current_clean = calculate_clean_checksum(current_bytes)
    receipt["before"] = {"exists": True, "clean_checksum": current_clean}
    if expected_before and current_clean != expected_before:
        raise Exception(f"expected_checksum_before mismatch: expected {expected_before}, found {current_clean}")
    backup = backup_and_rotate(target)
    receipt["backup"] = backup
    if dry_run:
        receipt["status"] = "DRY_RUN"
        logger.info(f"DRY-RUN: would delete {target}")
        return
    os.remove(target)
    receipt["status"] = "SUCCESS"
    logger.info(f"Deleted target '{target}' (backup at {backup})")

def action_patch(target: str, patch_file: str, start_marker: str, end_marker: str, regex: bool, occurrence: str, expected_before: Optional[str], dry_run: bool, logger, receipt: Dict[str, Any]) -> None:
    """
    Patch the target by replacing the first/last/nth occurrence between start_marker and end_marker with contents of patch_file.
    If start_marker or end_marker is empty string, supports single-marker replacement if patch_file contains anchors, otherwise error.
    """
    receipt["action"] = "patch"
    if not os.path.exists(target):
        raise FileNotFoundError(f"Target '{target}' not found for patching.")
    if not os.path.exists(patch_file):
        raise FileNotFoundError(f"Patch file '{patch_file}' not found.")

    original = safe_read(target) or b""
    original_clean = calculate_clean_checksum(original)
    receipt["before"] = {"clean_checksum": original_clean, "size": len(original)}
    if expected_before and original_clean != expected_before:
        raise Exception(f"expected_checksum_before mismatch: expected {expected_before}, found {original_clean}")

    try:
        patch_bytes = safe_read(patch_file) or b""
        try:
            patch_text = patch_bytes.decode('utf-8-sig')
        except Exception:
            patch_text = patch_bytes.decode('latin-1', errors='replace')
        try:
            orig_text = original.decode('utf-8-sig')
        except Exception:
            orig_text = original.decode('latin-1', errors='replace')
    except Exception as e:
        raise Exception(f"Failed to read files: {e}")

    # remove trailing checksum tags from original before patching to avoid duplication
    orig_text_cleaned, removed_tags_count = remove_all_checksum_tags_from_text(orig_text)
    if removed_tags_count:
        logger.info(f"Removed {removed_tags_count} existing checksum tag(s) from target prior to patching.")
    # find region(s)
    if regex:
        flags = re.DOTALL
        if start_marker == "" and end_marker == "":
            raise ValueError("For regex mode you must provide a pattern (use start_marker as regex).")
        pattern = f"{start_marker}(.*?){end_marker}" if end_marker else start_marker
        if occurrence == "first":
            new_text, count = re.subn(pattern, lambda m: start_marker + patch_text + (end_marker or ""), orig_text_cleaned, count=1, flags=flags)
        elif occurrence == "last":
            matches = list(re.finditer(pattern, orig_text_cleaned, flags=flags))
            if not matches:
                raise ValueError("Markers not found for patch.")
            last = matches[-1]
            new_text = orig_text_cleaned[:last.start()] + (start_marker + patch_text + (end_marker or "")) + orig_text_cleaned[last.end():]
            count = 1
        else:
            # nth not implemented for regex in this simple version
            raise NotImplementedError("Occurrence 'nth' not supported for regex mode.")
    else:
        # plain text markers
        if start_marker == "" or end_marker == "":
            raise ValueError("For plain-text patch you must provide both start_marker and end_marker.")
        # build region to replace
        region = start_marker + "(CONTENT)" + end_marker
        # find occurrences
        occurrences = []
        idx = 0
        while True:
            s = orig_text_cleaned.find(start_marker, idx)
            if s == -1:
                break
            e = orig_text_cleaned.find(end_marker, s + len(start_marker))
            if e == -1:
                break
            occurrences.append((s, e + len(end_marker)))
            idx = e + len(end_marker)
        if not occurrences:
            raise ValueError("Markers not found in target file.")
        if occurrence == "first":
            sel = occurrences[0]
        elif occurrence == "last":
            sel = occurrences[-1]
        else:
            # nth (1-based)
            n = int(occurrence)
            if n <= 0 or n > len(occurrences):
                raise ValueError("Invalid occurrence index.")
            sel = occurrences[n-1]
        new_text = orig_text_cleaned[:sel[0]] + start_marker + patch_text + end_marker + orig_text_cleaned[sel[1]:]

    # finalize: remove any existing checksum tags and append one computed from patched content
    new_text_stripped, _ = remove_all_checksum_tags_from_text(new_text)
    new_clean = hashlib.sha256(new_text_stripped.replace("\r\n", "\n").encode('utf-8')).hexdigest()
    # add checksum tag at end
    new_with_tag = (new_text_stripped.rstrip() + "\n\n" + f"<!-- [ARK_INTEGRITY_CHECKSUM::sha256:{new_clean}] -->\n")

    receipt["patch"] = {"patch_file": patch_file, "removed_tags": removed_tags_count, "new_clean": new_clean}
    # backup
    backup = backup_and_rotate(target)
    receipt["backup"] = backup

    if dry_run:
        logger.info("DRY-RUN: patch would be applied (no changes written).")
        receipt["status"] = "DRY_RUN"
        return

    # write atomically
    atomic_write_file(target, new_with_tag.encode('utf-8'))
    written = safe_read(target) or b""
    verify_clean = calculate_clean_checksum(written)
    if verify_clean != new_clean:
        # rollback
        if backup:
            shutil.copy2(backup, target)
        raise Exception(f"Post-write verification failed: expected {new_clean}, found {verify_clean}")

    receipt["after"] = {"clean_checksum": verify_clean, "size": len(written)}
    receipt["status"] = "SUCCESS"
    logger.info(f"Patch applied to '{target}' successfully (backup at {backup}).")

# ---------- CLI / main ----------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ARK Universal Updater")
    p.add_argument("--mode", choices=["replace", "delete", "patch"], required=True)
    p.add_argument("--target", required=True, help="Relative path to target file (from repo root).")
    p.add_argument("--source", help="Source file in staging (for replace).")
    p.add_argument("--expected-before", help="Expected clean checksum of target before operation (SHA256).")
    p.add_argument("--dry-run", action="store_true")
    # patch-specific
    p.add_argument("--patch-file", help="Patch file path in staging (for patch mode).")
    p.add_argument("--start-marker", default="", help="Start marker for patch (plain text or regex).")
    p.add_argument("--end-marker", default="", help="End marker for patch (plain text or regex).")
    p.add_argument("--regex", action="store_true", help="Interpret markers as regex (use start-marker as pattern if end empty).")
    p.add_argument("--occurrence", default="first", help="first | last | nth (1-based index as string).")
    return p

def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    # basic logger (stdout + receipt file)
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger("ark.updater")

    receipt: Dict[str, Any] = {
        "timestamp": now_ts(),
        "mode": args.mode,
        "target": args.target,
        "dry_run": args.dry_run,
        "status": "PENDING",
        "notes": []
    }

    target_path = os.path.abspath(os.path.join(ROOT_DIR, args.target))

    if not acquire_lock(logger):
        logger.critical("Updater lock not acquired. Exiting.")
        sys.exit(1)

    try:
        if args.mode == "replace":
            if not args.source:
                raise ValueError("replace mode requires --source")
            source_path = os.path.abspath(args.source) if os.path.isabs(args.source) else os.path.abspath(os.path.join(STAGING_DIR, args.source))
            action_replace(target_path, source_path, args.expected_before, args.dry_run, logger, receipt)

        elif args.mode == "delete":
            action_delete(target_path, args.expected_before, args.dry_run, logger, receipt)

        elif args.mode == "patch":
            if not args.patch_file:
                raise ValueError("patch mode requires --patch-file")
            patch_path = os.path.abspath(args.patch_file) if os.path.isabs(args.patch_file) else os.path.abspath(os.path.join(STAGING_DIR, args.patch_file))
            action_patch(target_path, patch_path, args.start_marker, args.end_marker, args.regex, args.occurrence, args.expected_before, args.dry_run, logger, receipt)

        else:
            raise ValueError("Unknown mode")

    except Exception as e:
        logger.exception(f"Updater failed: {e}")
        receipt["status"] = "FAIL"
        receipt["error"] = str(e)
        # Try not to leave a partial temp file (best-effort)
        sys.exit(1)
    finally:
        # save receipt
        try:
            fname = os.path.join(RECEIPT_DIR, f"updater_receipt_{now_ts()}.json")
            with open(fname, "w", encoding="utf-8") as rf:
                json.dump(receipt, rf, ensure_ascii=False, indent=2)
            logger.info(f"Receipt saved to {fname}")
        except Exception as e:
            logger.error(f"Failed to write receipt: {e}")
        release_lock(logger)

if __name__ == "__main__":
    main()
