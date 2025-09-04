# diagnose_write_read.py
import os, sys, hashlib, tempfile, codecs, time
from pathlib import Path

CHECKSUM_TAG_FORMAT = "<!-- [ARK_INTEGRITY_CHECKSUM::sha256:{}] -->"
CHECKSUM_TAG_PATTERN_BYTES = (
    rb'<!--\s*\[ARK_INTEGRITY_CHECKSUM::sha256:[a-f0-9]{64}\]\s*-->\s*\r?\n?'
)

def hexdump_prefix(b, n=128):
    return ' '.join(f"{x:02x}" for x in b[:n])

def calculate_clean_checksum_bytes(b: bytes, normalize_text=True):
    # remove BOM
    if b.startswith(codecs.BOM_UTF8):
        b = b[len(codecs.BOM_UTF8):]
    # normalize CRLF -> LF
    b = b.replace(b'\r\n', b'\n')
    # attempt text normalization only if asked and decodable
    if normalize_text:
        try:
            s = b.decode('utf-8')
            import unicodedata
            s = unicodedata.normalize('NFC', s)
            b = s.encode('utf-8')
        except Exception:
            pass
    import re
    b = re.sub(CHECKSUM_TAG_PATTERN_BYTES, b'', b)
    import hashlib
    return hashlib.sha256(b).hexdigest(), b

def test_write_and_verify(target_path, content_bytes):
    target_path = Path(target_path)
    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    print("Will write to:", target_path)
    expected_hash, clean_bytes = calculate_clean_checksum_bytes(content_bytes)
    print("Expected clean hash (prewrite):", expected_hash)
    # write temp
    with tempfile.NamedTemporaryFile('wb', delete=False, dir=str(target_dir), suffix=".tmp") as tf:
        tf.write(content_bytes)
        tf.flush()
        os.fsync(tf.fileno())             # <- IMPORTANT
        tmpname = tf.name
    print("Temp file written:", tmpname, "size:", os.path.getsize(tmpname))
    # atomic replace
    os.replace(tmpname, str(target_path))
    print("Replaced into:", target_path)
    # small pause to let FS settle
    time.sleep(0.1)
    # read back
    with open(target_path, 'rb') as f:
        read_bytes = f.read()
    verified_hash, verified_clean_bytes = calculate_clean_checksum_bytes(read_bytes)
    print("Verified clean hash (postwrite):", verified_hash)
    print("Sizes: pre-write(clean bytes)={}, post-read(raw)={}".format(len(clean_bytes), len(read_bytes)))
    if verified_hash != expected_hash or read_bytes != content_bytes:
        print("MISMATCH DETECTED")
        print("Prewrite bytes prefix:", hexdump_prefix(content_bytes))
        print("Postread bytes prefix :", hexdump_prefix(read_bytes))
        print("Prewrite len:", len(content_bytes), "Postread len:", len(read_bytes))
        print("Stat (target):", os.stat(target_path))
    else:
        print("OK: write/read identical and hashes match.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python diagnose_write_read.py path/to/target.md")
        sys.exit(1)
    sample_file = sys.argv[1]
    # example content: create predictable content with LF only
    content = "LINE1\nLINE2\nLINE3\n"
    # ensure you include the tag scenario if needed:
    # content_bytes = content.encode('utf-8')  # without tag
    import sys
    content_bytes = content.encode('utf-8')
    test_write_and_verify(sample_file, content_bytes)
