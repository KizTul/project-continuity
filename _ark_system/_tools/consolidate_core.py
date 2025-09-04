import os
import hashlib
import re
import json
import tempfile
from pathlib import Path

# --- КОНФИГУРАЦИЯ ---
TARGET_DIRECTORY = Path("_ark_system")
FILE_EXTENSION = ".md"
# УЛУЧШЕННЫЙ РЕГЭКСП: корректно обрабатывает тег с предшествующим переносом строки
CHECKSUM_TAG_PATTERN = re.compile(r'(?:\r?\n)?<!--\s*\[ARK_INTEGRITY_CHECKSUM::sha256:([a-f0-9]{64})\]\s*-->\s*\Z', re.IGNORECASE)
MANIFEST_PATH = TARGET_DIRECTORY / "ARK_INTEGRITY_MANIFEST.json"
ENCODING = 'utf-8'

def calculate_sha256(data: bytes) -> str:
    """Вычисляет SHA-256 хэш для байтовой строки."""
    return hashlib.sha256(data).hexdigest()

def process_file(file_path: Path) -> dict:
    """
    Обрабатывает один файл. Возвращает словарь с результатом для манифеста.
    """
    print(f"INFO: Processing file: {file_path}")
    try:
        original_content_bytes = file_path.read_bytes()
        original_content_str = original_content_bytes.decode(ENCODING)

        clean_content_str = CHECKSUM_TAG_PATTERN.sub('', original_content_str).rstrip()
        clean_content_bytes = clean_content_str.encode(ENCODING)

        clean_checksum = calculate_sha256(clean_content_bytes)
        
        new_tag = f"\n\n<!-- [ARK_INTEGRITY_CHECKSUM::sha256:{clean_checksum}] -->"
        
        final_content_str = clean_content_str + new_tag
        final_content_bytes = final_content_str.encode(ENCODING)
        
        final_checksum = calculate_sha256(final_content_bytes)

        # УЛУЧШЕННАЯ АТОМАРНАЯ ЗАПИСЬ
        with tempfile.NamedTemporaryFile('wb', dir=file_path.parent, delete=False) as tmp_file:
            tmp_file.write(final_content_bytes)
            # Гарантированный сброс буферов на диск
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            temp_path = Path(tmp_file.name)
        
        os.replace(temp_path, file_path)

        print(f"SUCCESS: File '{file_path}' updated. Final checksum: {final_checksum}")
        
        # УЛУЧШЕННЫЙ МАНИФЕСТ: сохраняем оба хэша
        return {
            "path": str(file_path.as_posix()),
            "status": "success",
            "clean_checksum": clean_checksum,
            "final_checksum": final_checksum
        }

    except Exception as e:
        error_message = str(e)
        print(f"ERROR: Failed to process file '{file_path}': {error_message}")
        # УЛУЧШЕННЫЙ МАНИФЕСТ: логируем ошибку
        return {
            "path": str(file_path.as_posix()),
            "status": "error",
            "error_details": error_message
        }

def main():
    """
    Основная функция: обходит директорию, обрабатывает файлы и создает манифест.
    """
    print("--- [ARK Core Consolidation Protocol v1.1] ---")
    
    if not TARGET_DIRECTORY.is_dir():
        print(f"FATAL: Target directory '{TARGET_DIRECTORY}' not found.")
        return

    manifest_data = []
    
    # Исключаем сам манифест из обработки
    files_to_process = [
        p for p in TARGET_DIRECTORY.rglob(f"*{FILE_EXTENSION}") 
        if p.resolve() != MANIFEST_PATH.resolve()
    ]

    for file_path in files_to_process:
        result = process_file(file_path)
        if result:
            manifest_data.append(result)

    try:
        manifest_content = json.dumps(manifest_data, indent=2)
        MANIFEST_PATH.write_text(manifest_content, encoding=ENCODING)
        print(f"SUCCESS: Integrity manifest created at '{MANIFEST_PATH}'")
    except Exception as e:
        print(f"ERROR: Failed to write manifest file: {e}")

    print("--- [Consolidation Complete] ---")

if __name__ == "__main__":
    main()