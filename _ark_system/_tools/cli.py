# -*- coding: utf-8 -*-
import subprocess
import sys

try:
    import pyperclip
except ImportError:
    print("[ARK CLI ENGINE] Fatal Error: 'pyperclip' library not found.")
    print("This is a one-time setup. Please run this command:")
    print("pip install -r requirements.txt")
    sys.exit(1)

def main():
    """Execute a system command, format the output as a receipt, and copy to clipboard."""
    # The .bat wrapper ensures we are always in the correct project root directory.
    if len(sys.argv) < 2:
        print("Usage: ARK_Run_Command.bat \"your full command here\"", file=sys.stderr)
        return

    command_to_run = " ".join(sys.argv[1:])

    try:
        result = subprocess.run(
            command_to_run, 
            shell=True, 
            capture_output=True, 
            text=True, 
            encoding="utf-8",
            errors='replace'
        )

        output = result.stdout.strip()
        if result.stderr:
            output += "\n--- STDERR ---\n" + result.stderr.strip()
        if not output:
            output = "[no output]"

        receipt = (
            f"--- ARK COMMAND EXECUTION RECEIPT ---\n"
            f"COMMAND EXECUTED:\n{command_to_run}\n\n"
            f"EXIT CODE: {result.returncode}\n\n"
            f"OUTPUT:\n{output}"
        )

        try:
            pyperclip.copy(receipt)
            print(receipt)
            print("\n\n[ARK] SUCCESS: The receipt above has been copied to your clipboard.")
        except Exception as e:
            print(receipt)
            print(f"\n\n[ARK] WARNING: Could not copy to clipboard ({e})")

    except Exception as e:
        error_receipt = (
            f"--- ARK COMMAND EXECUTION RECEIPT ---\n"
            f"COMMAND EXECUTED:\n{command_to_run}\n\n"
            f"OUTPUT (CRITICAL FAILURE):\nError executing command: {e}"
        )
        try:
            pyperclip.copy(error_receipt)
        except Exception as e_clip:
            print(f"\n\n[ARK] WARNING: Could not copy to clipboard ({e_clip})")
        print(error_receipt)
        print("\n\n[ARK] FAILURE: The error receipt above has been copied to your clipboard.")

if __name__ == "__main__":
    main()
