import os, sys, json, shutil
from pathlib import Path

def get_config():
    config_path = Path(__file__).resolve().parent / "config.json"
    if not config_path.exists(): raise FileNotFoundError(f"Файл конфигурации не найден: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f: return json.load(f)

def deploy():
    print("--- ЗАПУСК ДЕПЛОЯ ЯДРА (Staging -> Production) ---")
    try:
        config = get_config()
        source_dir = Path(config["staging_directory"])
        destination_dir = Path(config["production_directory"])
        if not source_dir.is_dir(): raise FileNotFoundError(f"Директория-источник (песочница) не найдена: {source_dir}")
        if not destination_dir.is_dir(): raise FileNotFoundError(f"Директория назначения (рабочая) не найдена: {destination_dir}")
        print(f"\nИсточник:      {source_dir}\nНазначение:    {destination_dir}\n" + "-" * 50)
        ignore_dirs = {"_tools"}
        for item in sorted(source_dir.rglob('*')):
            if any(ignored in item.parts for ignored in ignore_dirs): continue
            relative_path = item.relative_to(source_dir)
            dest_path = destination_dir / relative_path
            if item.is_dir():
                if not dest_path.exists(): dest_path.mkdir(parents=True, exist_ok=True)
            elif item.is_file(): shutil.copy2(item, dest_path)
        print("\n[УСПЕХ] Деплой ЯДРА успешно завершен.")
    except Exception as e: print(f"\n[КРИТИЧЕСКАЯ ОШИБКА] {e}")
    finally: os.system("pause")

if __name__ == "__main__": sys.stdout.reconfigure(encoding='utf-8'); deploy()