# _ark_system/_tools/get_checksum.py
# Version: 3.0 - Synchronized with apply_modifications v11.1
import argparse
import sys
import os
import hashlib

# --- Ensure correct import path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# --- Import from the Single Source of Truth ---
from _ark_system._tools.ark_checksum import calculate_clean_checksum

def main():
    """
    Command-line interface for the ARK checksum utility.
    This script is a simple wrapper around the canonical logic in ark_checksum.py.
    """
    if sys.platform == "win32":
        os.system("chcp 65001 > nul")

    parser = argparse.ArgumentParser(description='Calculate the canonical SHA-256 checksum of a file.')
    parser.add_argument('file_path', help='The path to the file.')
    parser.add_argument('--raw', action='store_true', help='Calculate raw checksum without any normalization.')
    args = parser.parse_args()

    try:
        with open(args.file_path, 'rb') as f:
            content_bytes = f.read()
            
    except FileNotFoundError:
        # According to our protocol, a non-existent file is a specific state
        # that should be reported with a distinct exit code for the calling process to interpret.
        # The apply_modifications script relies on this behavior.
        print(f"Error: File not found at '{os.path.abspath(args.file_path)}'", file=sys.stderr)
        sys.exit(2)
        
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    if args.raw:
        # Raw mode bypasses the canonical function for a direct hash.
        checksum = hashlib.sha256(content_bytes).hexdigest()
    else:
        # Standard mode uses the imported "Golden Standard" function.
        checksum = calculate_clean_checksum(content_bytes)

    if checksum:
        print(checksum)
        sys.exit(0)
    else:
        # This branch is hit if calculate_clean_checksum returns None, indicating an internal error.
        print("Error: Checksum calculation failed.", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()