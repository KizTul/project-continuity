# apply_patch.py (v3.0 - "Атомарный Патч")
import os
import sys
import subprocess
import importlib.util

def run_command(command):
    """Выполняет команду в оболочке и возвращает True в случае успеха."""
    try:
        subprocess.run(command, check=True, shell=True, encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[!] ОШИБКА GIT: {e.stderr}")
        return False

def apply_modifications():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    mod_data_path = os.path.join(script_dir, "modification_data.py")
    
    print("--- [ ARK ATOMIC PATCH APPLICATOR v3.0 ] ---")
    print(f"Корень проекта: {project_root}")

    # 1. Загрузка патча
    try:
        spec = importlib.util.spec_from_file_location("modification_data", mod_data_path)
        mod_data = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod_data)
        modifications = mod_data.modifications
        commit_message = mod_data.commit_message
    except Exception as e:
        print(f"[!] КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить 'modification_data.py'.\n    {e}")
        return

    # 2. Применение изменений к файлам
    os.chdir(project_root)
    for mod in modifications:
        action = mod.get("action")
        path = mod.get("path")
        content = mod.get("content", "")
        
        print(f"\n[*] Применяю: {action} для '{path}'")
        try:
            if action == "CREATE_FILE":
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print("    [+] УСПЕХ: Файл создан.")
        except Exception as e:
            print(f"    [!] ОШИБКА ФАЙЛА: {e}")
            return # Прерываем выполнение при ошибке

    # 3. Синхронизация с Git
    print("\n[*] Начинаю синхронизацию с Git...")
    if not run_command("git add ."): return
    print("    [+] git add . - УСПЕХ")
    
    if not run_command(f'git commit -m "{commit_message}"'): return
    print(f'    [+] git commit -m "{commit_message}" - УСПЕХ')

    print("\n[*] Пытаюсь отправить на GitHub...")
    if not run_command("git push origin main"):
        print("\n[!] ПРЕДУПРЕЖДЕНИЕ: Не удалось отправить на GitHub. Изменения закоммичены локально.")
        print("    Попробуйте запустить 'ARK_Sync_System.bat' позже вручную.")
    else:
        print("    [+] git push - УСПЕХ")

    # 4. Самоочистка
    try:
        os.remove(mod_data_path)
        print("\n[*] Самоочистка: 'modification_data.py' удален.")
    except Exception as e:
        print(f"\n[!] ОШИБКА ОЧИСТКИ: {e}")

    print("\n--- [ ЗАВЕРШЕНО ] ---")

if __name__ == "__main__":
    apply_modifications()