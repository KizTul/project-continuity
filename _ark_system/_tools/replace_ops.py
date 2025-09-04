import re
import unicodedata

def _detect_eol(s: str) -> str:
    return '\\r\\n' if '\\r\\n' in s else '\\n'

def _normalize_text(s: str) -> str:
    if not isinstance(s, str):
        return s
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[\u00A0\u200B\u202F]", " ", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+$", "", s, flags=re.MULTILINE)
    return s

def replace_in_file_bytes(original_bytes: bytes, content) -> tuple[bytes, int]:
    """Возвращает (new_bytes, replacements_count)."""
    if isinstance(content, str):
        pattern = content
        replacement = ''
        regex = False
        ignore_ws = False
    else:
        pattern = content.get('pattern', '')
        replacement = content.get('replacement', '')
        regex = bool(content.get('regex', False))
        ignore_ws = bool(content.get('ignore_whitespace', False))

    original_text = original_bytes.decode('utf-8-sig')
    eol = _detect_eol(original_text)
    norm_text = _normalize_text(original_text)
    norm_pattern = _normalize_text(pattern)
    norm_replacement = _normalize_text(replacement)

    if ignore_ws and not regex:
        esc = re.escape(norm_pattern)
        esc = re.sub(r'(?:\\\n|\\t|\\ )+', r'\\s+', esc)
        rx = re.compile(esc, flags=re.DOTALL)
        new_norm_text, n = rx.subn(norm_replacement, norm_text, count=1)
    elif regex:
        rx = re.compile(norm_pattern, flags=re.DOTALL)
        new_norm_text, n = rx.subn(norm_replacement, norm_text, count=1)
    else:
        if norm_pattern in norm_text:
            new_norm_text = norm_text.replace(norm_pattern, norm_replacement, 1)
            n = 1
        else:
            return original_bytes, 0

    final_text = new_norm_text.replace('\\n', eol)
    return final_text.encode('utf-8'), n