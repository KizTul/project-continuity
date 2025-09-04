# ARK MODIFICATION PROCESSOR v8.0 - "Hardened"
# Incorporates all consultant recommendations for stability and security.

import argparse
import json
import os
import sys
import logging
import jsonschema
from datetime import datetime
import hashlib
from tempfile import NamedTemporaryFile
import time
import shutil
from glob import glob
from typing import Optional, Tuple

# --- Constants ---
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
STAGING_DIR = os.path.join(ROOT_DIR, '_ark_system', '_staging')
MOD_PACKAGE_PATH = os.path.join(STAGING_DIR, 'modification_package.json')
LOG_DIR = os.path.join(ROOT_DIR, '_ark_system', 'logs')
RECEIPT_DIR = os.path.join(LOG_DIR, 'receipts')
BACKUP_DIR = os.path.join(ROOT_DIR, '_ark_system', 'backup')
LOCK_FILE_PATH = os.path.join(STAGING_DIR, '.apply.lock')

# --- Schemas & Formats ---
MODIFICATION_SCHEMA_V1_1 = {
    "type": "object",
    "properties": {
        "version": {"type": "string", "pattern": "^1\\.1$"},
        "modifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": [
                        "CREATE_FILE", "MODIFY_FILE", "DELETE_FILE", "REPLACE_IN_FILE",
                        "CREATE_DIRECTORY", "APPEND_TO_FILE", "APPEND_TO_JSON_ARRAY"
                    ]},
                    "path": {"type": "string"},
                    "content": {"type": ["string", "object"]},
                    "expected_checksum_before": {"type": ["string", "null"]}
                },
                "required": ["action", "path"]
            }
        }
    },
    "required": ["version", "modifications"]
}
CHECKSUM_TAG_FORMAT = "<!-- [ARK_INTEGRITY_CHECKSUM::sha256:{}] -->"
DEFAULT_MARKERS = ['...', '[...', ']...', 'остается без изменений', 'без изменений', 'no change', 'unchanged']
# Explicitly import from a single source of truth for checksum logic
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
from ark_checksum import calculate_clean_checksum, extract_checksum_tag

# --- Utility Functions ---

class SecurityException(Exception):
    pass

def setup_logging(log_path):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(log_path, encoding='utf-8'), logging.StreamHandler()]
    )
    return logging.getLogger()

def ensure_parent_dir(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

def safe_path(base, sub_path):
    full = os.path.abspath(os.path.join(base, sub_path))
    abs_base = os.path.abspath(base)
    if os.path.commonpath([abs_base, full]) != abs_base:
        raise SecurityException(f"Path '{sub_path}' is outside base '{base}'")
    return full

def _read_file_with_retry(path, logger, attempts=3, delay=0.2):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            if not os.path.exists(path):
                return None # File not existing is a valid state, not an error.
            with open(path, 'rb') as f:
                return f.read()
        except Exception as e:
            last_exc = e
            logger.warning(f"Read attempt {attempt}/{attempts} for '{path}' failed: {e}")
            time.sleep(delay)
    logger.error(f"Failed to read file '{path}' after {attempts} attempts.")
    if last_exc:
        raise last_exc
    return None # Should not be reached if an exception was caught

def create_backup_and_rotate(file_path: str, backup_dir: str, max_backups: int = 5) -> Optional[str]:
    if not os.path.exists(file_path):
        return None
    ensure_parent_dir(backup_dir)
    base_name = os.path.basename(file_path)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"{base_name}.{ts}.bak"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(file_path, backup_path)
    # Rotation logic
    pattern = os.path.join(backup_dir, f"{base_name}.*.bak")
    files = sorted(glob(pattern), key=os.path.getmtime)
    while len(files) > max_backups:
        os.remove(files.pop(0))
    return backup_path

def detect_truncation_or_placeholder(original_bytes: bytes, candidate_bytes: bytes) -> Tuple[bool, str]:
    if not original_bytes:
        return False, "" # Cannot determine truncation if original is empty
    len_orig = len(original_bytes)
    len_cand = len(candidate_bytes)

    if len_cand < len_orig * 0.5: # 50% reduction threshold
        reason = f"SIZE_REDUCTION: original={len_orig}, new={len_cand}, reduction={1 - len_cand/len_orig:.2%}"
        return True, reason

    try:
        cand_lower_str = candidate_bytes.decode('utf-8').lower()
        for marker in DEFAULT_MARKERS:
            if marker.lower() in cand_lower_str:
                return True, f"PLACEHOLDER_MARKER_FOUND: {marker}"
    except UnicodeDecodeError:
        pass # Not a text file, skip marker check
    return False, ""

def replace_in_file_logic(original_bytes: bytes, content_spec: dict) -> tuple[bytes, int]:
    try:
        original_text = original_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        original_text = original_bytes.decode('latin-1', errors='replace') # Graceful fallback
    
    pattern = content_spec.get('pattern', '')
    replacement = content_spec.get('replacement', '')
    is_regex = bool(content_spec.get('regex', False))

    if is_regex:
        new_text, count = re.subn(pattern, replacement, original_text, count=1, flags=re.DOTALL)
    else:
        new_text, count = original_text.replace(pattern, replacement, 1), 1 if pattern in original_text else 0

    return new_text.encode('utf-8'), count

# --- Transaction Class ---
class Transaction:
    def __init__(self, operations, logger, dry_run=False):
        self.operations = operations
        self.logger = logger
        self.dry_run = dry_run
        self.undo_log = []
        self.receipt = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "PENDING",
            "dry_run": self.dry_run,
            "operation_count": len(self.operations),
            "actions": [],
            "updated_files": [],
            "rollback_errors": []
        }

    def execute(self):
        self.logger.info(f"--- [ARK Modification Processor v8.0 - Hardened] ---")
        try:
            for i, op in enumerate(self.operations):
                self.process_operation(i + 1, op)
            self.receipt["status"] = "SUCCESS"
        except Exception as e:
            self.logger.error(f"FATAL ERROR during execution: {e}", exc_info=True)
            self.receipt["status"] = "FAIL"
            self.logger.warning("--- [Initiating ROLLBACK] ---")
            self.rollback()
            self.logger.warning("--- [ROLLBACK Complete] ---")

    def rollback(self):
        for undo_op in reversed(self.undo_log):
            try:
                if undo_op['action'] == 'RESTORE_FILE':
                    shutil.move(undo_op['backup_path'], undo_op['original_path'])
                    self.logger.info(f"ROLLED BACK: Restored '{undo_op['original_path']}'")
                elif undo_op['action'] == 'DELETE_FILE':
                    if os.path.exists(undo_op['path']): os.remove(undo_op['path'])
                    self.logger.info(f"ROLLED BACK: Deleted '{undo_op['path']}'")
            except Exception as e:
                self.logger.error(f"ROLLBACK FAILED for {undo_op}: {e}", exc_info=True)
                self.receipt['rollback_errors'].append(str(e))

    def process_operation(self, i, op):
        action = op.get('action')
        path = op.get('path')
        full_path = safe_path(ROOT_DIR, path)
        self.logger.info(f"--- Step {i}/{len(self.operations)}: [{action}] on [{path}] ---")

        # --- State Verification ---
        original_bytes = _read_file_with_retry(full_path, self.logger)
        actual_checksum = calculate_clean_checksum(original_bytes if original_bytes is not None else b"")
        expected_checksum = op.get('expected_checksum_before')
        if expected_checksum is not None and actual_checksum != expected_checksum:
            raise Exception(f"STATE CONFLICT on '{path}'. Expected '{expected_checksum}', found '{actual_checksum}'.")

        # --- Prepare Undo Log ---
        if os.path.exists(full_path):
            backup_path = create_backup_and_rotate(full_path, BACKUP_DIR)
            if backup_path:
                self.undo_log.append({'action': 'RESTORE_FILE', 'original_path': full_path, 'backup_path': backup_path})
                self.logger.info(f"BACKUP: Saved '{path}' to {os.path.basename(backup_path)}.")
        else:
            self.undo_log.append({'action': 'DELETE_FILE', 'path': full_path})
        
        # --- Prepare Content ---
        final_content_bytes = b''
        if action in ['CREATE_FILE', 'MODIFY_FILE']:
            final_content_bytes = op.get('content', '').encode('utf-8')
        elif action == 'REPLACE_IN_FILE':
            if original_bytes is None: raise FileNotFoundError(f"Cannot replace in non-existent file: {path}")
            final_content_bytes, count = replace_in_file_logic(original_bytes, op.get('content', {}))
            if count == 0: self.logger.warning("REPLACE_IN_FILE: Pattern not found, file will be identical.")

        # --- Data Loss Guard ---
        if action == 'MODIFY_FILE' and original_bytes:
            should_abort, reason = detect_truncation_or_placeholder(original_bytes, final_content_bytes)
            if should_abort: raise Exception(f"DATA LOSS GUARD: Aborting. Reason: {reason}")
        
        # --- Perform Write ---
        final_clean_checksum = calculate_clean_checksum(final_content_bytes)
        is_verifiable = path.endswith('.md')
        
        if not self.dry_run:
            ensure_parent_dir(full_path)
            with NamedTemporaryFile('wb', delete=False, dir=os.path.dirname(full_path), suffix='.tmp') as tf:
                tf.write(final_content_bytes)
                if is_verifiable:
                    tag = f"\n\n{CHECKSUM_TAG_FORMAT.format(final_clean_checksum)}"
                    tf.write(tag.encode('utf-8'))
                tf.flush()
                os.fsync(tf.fileno())
                tmp_name = tf.name
            os.replace(tmp_name, full_path)

        # --- Post-Write Verification ---
        if not self.dry_run:
            time.sleep(0.05) # Brief pause for FS to catch up
            # Read back and verify
            read_back_bytes = _read_file_with_retry(full_path, self.logger)
            if read_back_bytes is None: raise IOError("Post-write verification failed: file is unreadable.")
            
            verified_clean_checksum = calculate_clean_checksum(read_back_bytes)
            if final_clean_checksum != verified_clean_checksum:
                raise IOError(f"POST-WRITE VERIFICATION FAILED! Expected checksum {final_clean_checksum}, but found {verified_clean_checksum} on disk.")
            self.logger.info(f"SUCCESS: File '{path}' processed and verified.")

        self.receipt['actions'].append({"action": action, "path": path, "status": "SUCCESS"})
        self.receipt['updated_files'].append({"path": path, "new_checksum": final_clean_checksum})
        
# --- Main Execution ---
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(RECEIPT_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    log_ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    log_path = os.path.join(LOG_DIR, f'apply_changes_{log_ts}.log')
    logger = setup_logging(log_path)
    
    transaction = None
    try:
        with open(LOCK_FILE_PATH, 'x') as lf:
            lf.write(str(os.getpid()))
        logger.info(f"Lock acquired by PID {os.getpid()}.")

        with open(MOD_PACKAGE_PATH, 'r', encoding='utf-8') as f:
            package_data = json.load(f)
        jsonschema.validate(instance=package_data, schema=MODIFICATION_SCHEMA_V1_1)
        
        transaction = Transaction(package_data.get('modifications', []), logger, args.dry_run)
        transaction.execute()

    except Exception as e:
        logger.critical(f"An unhandled exception occurred in main block: {e}", exc_info=True)
        if transaction:
            transaction.receipt["status"] = "FAIL"
    finally:
        if transaction:
            receipt_path = os.path.join(RECEIPT_DIR, f'receipt_{log_ts}.json')
            try: # Atomic write for receipt
                with NamedTemporaryFile('w', delete=False, dir=RECEIPT_DIR, suffix='.tmp', encoding='utf-8') as tf:
                    json.dump(transaction.receipt, tf, indent=2)
                    tf.flush()
                    os.fsync(tf.fileno())
                    tmp_name = tf.name
                os.replace(tmp_name, receipt_path)
                logger.info(f"Receipt saved to {receipt_path}")
            except Exception as e:
                logger.error(f"Failed to save receipt atomically: {e}", exc_info=True)

        if os.path.exists(LOCK_FILE_PATH):
            os.remove(LOCK_FILE_PATH)
            logger.info("Lock file released.")

if __name__ == '__main__':
    main()