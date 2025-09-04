# _ark_system/_tools/ark_checksum.py
# Version: 2.0 - Synchronized with apply_modifications v11.1
import hashlib
import re
from typing import Optional, Union
import codecs
from charset_normalizer import detect

# --- Constants (Mirrors apply_modifications.py) ---
BOM_BYTES = b'\xef\xbb\xbf'
CHECKSUM_TAG_PATTERN_BYTES = re.compile(
    rb'(\r?\n)*<!--\s*\[ARK_INTEGRITY_CHECKSUM::sha256:[a-f0-9]{64}\]\s*-->\s*\Z',
    flags=re.IGNORECASE
)

# --- Canonical Logic (Mirrors apply_modifications.py) ---
def _canonicalize_bytes_for_hash(raw: Optional[bytes]) -> bytes:
    """Normalizes byte string for consistent hashing."""
    if raw is None:
        return b''
    if raw.startswith(BOM_BYTES):
        raw = raw[len(BOM_BYTES):]
    raw = raw.replace(b'\r\n', b'\n')
    raw = CHECKSUM_TAG_PATTERN_BYTES.sub(b'', raw)
    raw = raw.rstrip(b'\n')
    return raw

def decode_safely(data: bytes) -> str:
    """Decodes bytes using detected encoding, falling back to latin-1."""
    if not data:
        return ""
    result = detect(data)
    encoding = result.get('encoding', 'utf-8')
    try:
        # Use utf-8-sig to handle BOM correctly during decode
        if encoding == 'utf-8' and data.startswith(BOM_BYTES):
            return data.decode('utf-8-sig')
        return data.decode(encoding)
    except (UnicodeDecodeError, TypeError):
        return data.decode('latin-1', errors='replace')

def calculate_clean_checksum(data: Union[bytes, str, None]) -> Optional[str]:
    """Calculates the canonical SHA-256 hash, mirroring the full logic of apply_modifications.py."""
    if data is None:
        return hashlib.sha256(b'').hexdigest()
    try:
        if isinstance(data, str):
            data_bytes = data.encode('utf-8')
        else:
            data_bytes = data
        
        # This logic is intentionally simpler than apply_modifications because this tool
        # only ever receives raw bytes from a file read. The complex part is in apply_modifications.
        # Here we just need to ensure the normalization is identical.
        canon_bytes = _canonicalize_bytes_for_hash(data_bytes)
        return hashlib.sha256(canon_bytes).hexdigest()
    except Exception:
        return None