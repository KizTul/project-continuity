# _ark_system/_tools/apply_modifications.py
# Version: 11.2 - Fixed checksum duplication issue
import argparse
import json
import os
import sys
import logging
import jsonschema
from datetime import datetime, timezone
import hashlib
from tempfile import NamedTemporaryFile
import time
import shutil
from glob import glob
from typing import Optional, Tuple, Set, Dict, Any, List
from charset_normalizer import detect
import psutil
import codecs
import re

# --- Ensure correct import path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# --- Import from the Single Source of Truth ---
from _ark_system._tools.ark_checksum import calculate_clean_checksum

# --- Constants & Paths ---
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
STAGING_DIR = os.path.join(ROOT_DIR, '_ark_system', '_staging')
MOD_PACKAGE_PATH = os.path.join(STAGING_DIR, 'modification_package.json')
LOG_DIR = os.path.join(ROOT_DIR, '_ark_system', 'logs')
RECEIPT_DIR = os.path.join(LOG_DIR, 'receipts')
BACKUP_DIR = os.path.join(ROOT_DIR, '_ark_system', 'backup')
LOCK_FILE_PATH = os.path.join(STAGING_DIR, '.apply.lock')
EMPTY_FILE_CHECKSUM = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
CHECKSUM_TAG_FORMAT = "<!-- [ARK_INTEGRITY_CHECKSUM::sha256:{}] -->"
CHECKSUM_TAG_REGEX = r"<!-- \[ARK_INTEGRITY_CHECKSUM::sha256:[0-9a-f]{64}\] -->"
DEFAULT_MARKERS = ['...', '[...', ']...', 'остается без изменений', 'без изменений', 'no change', 'unchanged']
SELF_VERIFYING_EXTENSIONS = ['.md']

# --- Schemas & Self-Verification ---
MODIFICATION_SCHEMA_V1_1 = {
    "type": "object",
    "required": ["version", "modifications"],
    "properties": {
        "version": {"type": "string", "pattern": "^1\\.1$"},
        "modifications": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["action", "path"],
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "CREATE_FILE", "MODIFY_FILE", "DELETE_FILE",
                            "REPLACE_IN_FILE", "APPEND_TO_FILE", "CREATE_DIRECTORY",
                            "APPEND_TO_JSON_ARRAY"
                        ]
                    },
                    "path": {"type": "string"},
                    "content": {"type": ["string", "object", "array", "null"]},
                    "expected_checksum_before": {"type": ["string", "null"]}
                }
            }
        }
    }
}

IMPLEMENTED_ACTIONS: Set[str] = {
    "CREATE_FILE", "MODIFY_FILE", "DELETE_FILE", "REPLACE_IN_FILE",
    "APPEND_TO_FILE", "CREATE_DIRECTORY", "APPEND_TO_JSON_ARRAY"
}

def self_verify_actions():
    """Verify that all actions in schema are implemented."""
    declared_actions = set(
        MODIFICATION_SCHEMA_V1_1["properties"]["modifications"]["items"]["properties"]["action"]["enum"]
    )
    missing = declared_actions - IMPLEMENTED_ACTIONS
    if missing:
        raise NotImplementedError(
            f"FATAL: Unimplemented actions declared in schema: {sorted(list(missing))}"
        )

# --- Utilities ---
class SecurityException(Exception):
    pass

def setup_logging(log_path: str) -> logging.Logger:
    """Configure logging to file and console with UTF-8 encoding."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("ark.apply")

def ensure_parent_dir(path: str):
    """Ensure parent directory exists for the given path."""
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

def safe_path(base: str, sub_path: str) -> str:
    """Resolve path and ensure it stays within the base directory."""
    full = os.path.abspath(os.path.join(base, sub_path))
    abs_base = os.path.abspath(base)
    if os.path.commonpath([abs_base, full]) != abs_base:
        raise SecurityException(f"Path '{sub_path}' is outside base '{base}'")
    return full

def check_file_access(path: str, mode: int, logger: logging.Logger) -> bool:
    """Check if the process has the specified access permissions for the path."""
    if not os.access(path, mode):
        logger.error(f"No permission to access '{path}' with mode {mode}")
        return False
    return True

def _read_file_with_retry(path: str, logger: logging.Logger, attempts: int = 3, delay: float = 0.2) -> Optional[bytes]:
    """Read file content with retries in case of transient errors."""
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            if not os.path.exists(path):
                return None
            if not check_file_access(path, os.R_OK, logger):
                raise PermissionError(f"No read permission for '{path}'")
            with open(path, 'rb') as f:
                return f.read()
        except Exception as e:
            last_exc = e
            logger.warning(f"Read attempt {attempt}/{attempts} for '{path}' failed: {e}")
            time.sleep(delay)
    logger.error(f"Failed to read file '{path}' after {attempts} attempts.")
    if last_exc:
        raise last_exc
    return None

def create_backup_and_rotate(file_path: str, backup_dir: str, max_backups: int = 5) -> Optional[str]:
    """Create timestamped backup and rotate old backups. Returns backup path or None if file didn't exist."""
    if not os.path.exists(file_path):
        return None
    os.makedirs(backup_dir, exist_ok=True)
    base_name = os.path.basename(file_path)
    ts = datetime.utcnow().replace(tzinfo=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"{base_name}.{ts}.bak"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(file_path, backup_path)
    pattern = os.path.join(backup_dir, f"{base_name}.*.bak")
    files = sorted(glob(pattern), key=os.path.getmtime)
    while len(files) > max_backups:
        os.remove(files.pop(0))
    return backup_path

def detect_truncation_or_placeholder(original_bytes: Optional[bytes], candidate_bytes: bytes) -> Tuple[bool, str]:
    """Check if candidate content indicates truncation or placeholder text."""
    if not original_bytes:
        return False, ""
    len_orig = len(original_bytes)
    len_cand = len(candidate_bytes)
    if len_cand < len_orig * 0.5:
        reason = f"SIZE_REDUCTION: original={len_orig}, new={len_cand}, reduction={1 - len_cand/len_orig:.2%}"
        return True, reason
    try:
        cand_lower_str = candidate_bytes.decode('utf-8').lower()
        for marker in DEFAULT_MARKERS:
            if marker.lower() in cand_lower_str:
                return True, f"PLACEHOLDER_MARKER_FOUND: {marker}"
    except UnicodeDecodeError:
        pass
    return False, ""

def decode_file_content(data: bytes, logger: logging.Logger) -> str:
    """Decode file content using detected encoding, falling back to latin-1."""
    if not data:
        return ""
    result = detect(data)
    encoding = result.get('encoding', 'utf-8')
    try:
        return data.decode(encoding)
    except UnicodeDecodeError:
        logger.warning(f"Failed to decode with {encoding}, falling back to latin-1")
        return data.decode('latin-1', errors='replace')

def replace_in_file_logic(original_bytes: bytes, content_spec: dict) -> Tuple[bytes, int]:
    """Perform a replace operation on file content, supporting plain string or regex replacement."""
    original_text = decode_file_content(original_bytes, logging.getLogger("ark.apply"))
    pattern = content_spec.get('pattern', '')
    replacement = content_spec.get('replacement', '')
    is_regex = bool(content_spec.get('regex', False))

    if not pattern:
        return original_bytes, 0

    if is_regex:
        new_text, count = re.subn(pattern, replacement, original_text, count=1, flags=re.DOTALL)
    else:
        if pattern not in original_text:
            return original_bytes, 0
        new_text = original_text.replace(pattern, replacement, 1)
        count = 1

    if count == 0:
        return original_bytes, 0

    # Preserve newline style
    if '\r\n' in original_text and '\r\n' not in new_text:
        new_text = new_text.replace('\n', '\r\n')

    new_bytes = new_text.encode('utf-8')
    if original_bytes.startswith(codecs.BOM_UTF8) and not new_bytes.startswith(codecs.BOM_UTF8):
        new_bytes = codecs.BOM_UTF8 + new_bytes

    return new_bytes, count

# --- Transaction ---
class Transaction:
    def __init__(self, operations: List[Dict[str, Any]], logger: logging.Logger, dry_run: bool = False):
        self.operations = operations
        self.logger = logger
        self.dry_run = dry_run
        self.undo_log: List[Dict[str, Any]] = []
        self.receipt: Dict[str, Any] = {
            "timestamp": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "status": "PENDING",
            "dry_run": self.dry_run,
            "operation_count": len(operations),
            "actions": [],
            "updated_files": [],
            "rollback_errors": []
        }

    def execute(self):
        """Execute all operations in the transaction, with rollback on failure."""
        self.logger.info("--- [ARK Modification Processor v11.2 - Fixed] ---")
        try:
            if not self.operations and not self.dry_run:
                self.logger.info("No modifications to apply.")
                self.receipt["status"] = "NO_OP"
                return

            for i, op in enumerate(self.operations):
                self.process_operation(i + 1, op)

            if not self.receipt["updated_files"] and self.operations:
                self.receipt["status"] = "NO_OP"
            else:
                self.receipt["status"] = "SUCCESS"
        except Exception as e:
            self.logger.error(f"FATAL ERROR during execution: {e}", exc_info=True)
            self.receipt["status"] = "FAIL"
            self.logger.warning("--- [Initiating ROLLBACK] ---")
            self.rollback()
            self.logger.warning("--- [ROLLBACK Complete] ---")

    def rollback(self):
        """Revert changes made during the transaction."""
        for undo_op in reversed(self.undo_log):
            try:
                if undo_op['action'] == 'RESTORE_FILE':
                    shutil.move(undo_op['backup_path'], undo_op['original_path'])
                    self.logger.info(f"ROLLED BACK: Restored '{undo_op['original_path']}'")
                elif undo_op['action'] == 'DELETE_NEWLY_CREATED_FILE':
                    if os.path.exists(undo_op['path']):
                        os.remove(undo_op['path'])
                        self.logger.info(f"ROLLED BACK: Deleted newly created file '{undo_op['path']}'")
                elif undo_op['action'] == 'DELETE_DIR_IF_CREATED':
                    p = undo_op['path']
                    if os.path.isdir(p):
                        try:
                            os.rmdir(p)
                            self.logger.info(f"ROLLED BACK: Removed directory '{p}'")
                        except OSError:
                            self.logger.warning(f"Could not remove dir during rollback: {p}")
            except Exception as e:
                self.logger.error(f"ROLLBACK FAILED for {undo_op}: {e}", exc_info=True)
                self.receipt['rollback_errors'].append(str(e))

    def process_operation(self, i: int, op: Dict[str, Any]) -> None:
        """Process a single modification operation."""
        action: str = op.get('action', '')
        path: str = op.get('path', '')
        if not action or not path:
            raise ValueError(f"Operation {i} missing 'action' or 'path'")

        full_path = safe_path(ROOT_DIR, path)
        self.logger.info(f"--- Step {i}/{len(self.operations)}: [{action}] on [{path}] ---")

        original_bytes = _read_file_with_retry(full_path, self.logger)
        actual_checksum = calculate_clean_checksum(original_bytes)
        expected = op.get('expected_checksum_before')

        # Semantic Checksum Logic
        if expected is None and action != "CREATE_FILE":
            if original_bytes is None:
                raise Exception(f"STATE CONFLICT on '{path}'. Action '{action}' requires the file to exist, but it was not found.")
        elif expected is not None:
            if actual_checksum != expected:
                raise Exception(f"STATE CONFLICT on '{path}'. Expected '{expected}', found '{actual_checksum}'.")
        elif expected is None and action == "CREATE_FILE":
            if original_bytes is not None:
                raise Exception(f"STATE CONFLICT on '{path}'. Action 'CREATE_FILE' requires the file to be absent, but it exists with checksum '{actual_checksum}'.")

        final_content_bytes: Optional[bytes] = None
        if action in ('CREATE_FILE', 'MODIFY_FILE'):
            content_obj = op.get('content')
            if content_obj is None:
                raise ValueError(f"'content' is required for action '{action}' on '{path}'")
            if isinstance(content_obj, (dict, list)):
                content_str = json.dumps(content_obj, ensure_ascii=False, indent=2)
            else:
                content_str = str(content_obj)
            final_content_bytes = content_str.encode('utf-8')

        elif action == 'APPEND_TO_FILE':
            content_obj = op.get('content')
            if content_obj is None:
                raise ValueError(f"'content' is required for action '{action}' on '{path}'")
            if isinstance(content_obj, (dict, list)):
                content_str = json.dumps(content_obj, ensure_ascii=False, indent=2)
            else:
                content_str = str(content_obj)
            content_to_append = content_str.encode('utf-8')
            final_content_bytes = (original_bytes or b'') + content_to_append

        elif action == 'APPEND_TO_JSON_ARRAY':
            if original_bytes is None:
                base_array = []
            else:
                text = decode_file_content(original_bytes, self.logger)
                try:
                    base_array = json.loads(text)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in '{path}': {e}")
                if not isinstance(base_array, list):
                    raise ValueError("Target file does not contain a top-level JSON array.")
            to_append = op.get('content', [])
            if isinstance(to_append, list):
                base_array.extend(to_append)
            else:
                base_array.append(to_append)
            final_content_bytes = json.dumps(base_array, ensure_ascii=False, indent=2).encode('utf-8')

        elif action == 'REPLACE_IN_FILE':
            if original_bytes is None:
                raise FileNotFoundError(f"Cannot replace in non-existent file: {path}")
            if not check_file_access(full_path, os.R_OK | os.W_OK, self.logger):
                raise PermissionError(f"No read/write permission for '{full_path}'")
            final_content_bytes, count = replace_in_file_logic(original_bytes, op.get('content', {}))
            if count == 0:
                self.logger.warning(f"REPLACE_IN_FILE: Pattern not found in '{path}', skipping write.")
                self.receipt['actions'].append({"action": action, "path": path, "status": "NO_CHANGE", "reason": "pattern not found"})
                return

        elif action == 'DELETE_FILE':
            if os.path.exists(full_path):
                if not check_file_access(full_path, os.W_OK, self.logger):
                    raise PermissionError(f"No write permission for '{full_path}'")
                backup_path = create_backup_and_rotate(full_path, BACKUP_DIR)
                if backup_path:
                    self.undo_log.append({'action': 'RESTORE_FILE', 'original_path': full_path, 'backup_path': backup_path})
                if not self.dry_run:
                    os.remove(full_path)
            self.logger.info(f"SUCCESS: File '{path}' deleted.")
            self.receipt['actions'].append({"action": action, "path": path, "status": "SUCCESS"})
            return

        elif action == 'CREATE_DIRECTORY':
            if os.path.exists(full_path) and not os.path.isdir(full_path):
                raise ValueError(f"Cannot create directory '{path}': path exists and is not a directory")
            if not os.path.exists(full_path):
                if not self.dry_run:
                    try:
                        os.makedirs(full_path, exist_ok=True)
                    except OSError as e:
                        raise OSError(f"Failed to create directory '{path}': {e}")
                self.undo_log.append({'action': 'DELETE_DIR_IF_CREATED', 'path': full_path})
            self.logger.info(f"SUCCESS: Directory '{path}' ensured.")
            self.receipt['actions'].append({"action": action, "path": path, "status": "SUCCESS"})
            return

        else:
            raise ValueError(f"Unsupported action '{action}' in operation for '{path}'.")

        if action in ('MODIFY_FILE', 'REPLACE_IN_FILE') and original_bytes and final_content_bytes is not None:
            should_abort, reason = detect_truncation_or_placeholder(original_bytes, final_content_bytes)
            if should_abort:
                raise Exception(f"DATA LOSS GUARD: Aborting modification of '{path}'. Reason: {reason}")

        # --- NEW: strip old checksum tags before comparison ---
        def strip_tags(data: Optional[bytes]) -> bytes:
            if not data:
                return b""
            text = decode_file_content(data, self.logger)
            clean = re.sub(CHECKSUM_TAG_REGEX, "", text).strip()
            return clean.encode('utf-8')

        orig_clean = calculate_clean_checksum(strip_tags(original_bytes))
        new_clean = calculate_clean_checksum(strip_tags(final_content_bytes))

        if orig_clean == new_clean:
            self.logger.info(f"NO CHANGE: '{path}' content is identical after stripping tags. Skipping write.")
            self.receipt['actions'].append({"action": action, "path": path, "status": "NO_CHANGE"})
            return

        if final_content_bytes is None:
            raise ValueError(f"Internal error: final_content_bytes is None for action {action}")

        # Write file with checksum tag once
        ensure_parent_dir(full_path)
        if original_bytes:
            backup_path = create_backup_and_rotate(full_path, BACKUP_DIR)
            if backup_path:
                self.undo_log.append({'action': 'RESTORE_FILE', 'original_path': full_path, 'backup_path': backup_path})
        else:
            self.undo_log.append({'action': 'DELETE_NEWLY_CREATED_FILE', 'path': full_path})

        if not self.dry_run:
            # strip old tags before writing
            clean_bytes = strip_tags(final_content_bytes)
            checksum_value = calculate_clean_checksum(clean_bytes)
            tag = CHECKSUM_TAG_FORMAT.format(checksum_value)
            to_write = clean_bytes + b"\n" + tag.encode('utf-8') + b"\n"
            with NamedTemporaryFile('wb', delete=False, dir=os.path.dirname(full_path), suffix='.tmp') as tf:
                tf.write(to_write)
                tf.flush()
                os.fsync(tf.fileno())
                tmp_name = tf.name
            os.replace(tmp_name, full_path)

            # verify
            post_bytes = _read_file_with_retry(full_path, self.logger) or b""
            post_clean = calculate_clean_checksum(strip_tags(post_bytes))
            if post_clean != checksum_value:
                raise Exception(f"Post-write verification FAILED for '{path}'")

        self.logger.info(f"SUCCESS: Applied {action} to '{path}'")
        self.receipt['actions'].append({"action": action, "path": path, "status": "SUCCESS"})
        if path not in self.receipt['updated_files']:
            self.receipt['updated_files'].append(path)

# --- Main ---
def main():
    parser = argparse.ArgumentParser(description="Apply modification package to ARK system.")
    parser.add_argument('--dry-run', action='store_true', help="Simulate changes without applying them")
    args = parser.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(RECEIPT_DIR, exist_ok=True)

    log_file = os.path.join(LOG_DIR, f"apply_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.log")
    logger = setup_logging(log_file)

    self_verify_actions()

    transaction: Optional[Transaction] = None

    try:
        with open(LOCK_FILE_PATH, 'x') as lf:
            lf.write(str(os.getpid()))
        logger.info(f"Lock acquired by PID {os.getpid()}.")

        with open(MOD_PACKAGE_PATH, 'r', encoding='utf-8') as f:
            package_data = json.load(f)
        jsonschema.validate(instance=package_data, schema=MODIFICATION_SCHEMA_V1_1)

        transaction = Transaction(package_data.get('modifications', []), logger, args.dry_run)
        transaction.execute()

    except FileExistsError:
        logger.critical("Another apply process seems to be running (lock file exists). Abort.")
        if transaction:
            transaction.receipt["status"] = "FAIL"
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        if transaction:
            transaction.receipt["status"] = "FAIL"
    finally:
        if os.path.exists(LOCK_FILE_PATH):
            try:
                with open(LOCK_FILE_PATH, 'r') as lf:
                    pid = int(lf.read().strip())
                if pid == os.getpid() or not psutil.pid_exists(pid):
                    os.remove(LOCK_FILE_PATH)
                    logger.info("Lock released.")
                else:
                    logger.warning(f"Lock file belongs to another running process (PID {pid}), not removing.")
            except Exception as e:
                logger.warning(f"Failed to safely remove lock file: {e}")

    if transaction:
        receipt_name = f"receipt_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
        receipt_path = os.path.join(RECEIPT_DIR, receipt_name)
        try:
            with open(receipt_path, 'w', encoding='utf-8') as f:
                json.dump(transaction.receipt, f, ensure_ascii=False, indent=2)
            logger.info(f"Receipt saved at {receipt_path}")
        except Exception as e:
            logger.error(f"Failed to write receipt: {e}")

if __name__ == "__main__":
    main()
