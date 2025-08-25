# apply_patch.py (v4.0 - "Постоянный Инструмент")
import os
import sys
import base64
import subprocess
import importlib.util

def run_git_command(command, commit_message=""):
    """Выполняет Git команду, подставляя сообщение коммита."""
    final_command = command.replace("{commit_message}", commit_message)
    try:
        # Используем Popen для вывода в реальном времени
        process = subprocess.Popen(final_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        for line in process.stdout:
            print(line, end='')
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, final_command)
        return True
    except subprocess.CalledProcessError:
        return False
    except Exception as e:
        print(f"[!] Непредвиденная ошибка GIT: {e}")
        return False

def apply_modifications():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    mod_data_path = os.path.join(script_dir, "modification_data.py")
    
    print("--- [ ARK UNIVERSAL PATCH APPLICATOR v4.0 ] ---")
    
    # --- 1. Загрузка патча ---
    try:
        spec = importlib.util.spec_from_file_location("modification_data", mod_data_path)
        mod_data = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod_data)
        modifications = mod_data.modifications
        commit_message = getattr(mod_data, "commit_message", "") # Необязательное поле
    except Exception as e:
        print(f"[!] КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить 'modification_data.py'.\n    {e}")
        return

    # --- 2. Применение изменений к файлам ---
    os.chdir(project_root)
    for mod in modifications:
        action = mod.get("action")
        path = mod.get("path")
        print(f"\n[*] Применяю: {action} для '{path}'")
        try:
            content_raw = mod.get("content", "")
            content_b64 = mod.get("content_b64", None)

            # Определяем финальное содержимое
            if content_b64:
                content = base64.b64decode(content_b64).decode('utf-8')
            else:
                content = content_raw

            if action == "CREATE_OR_REPLACE_FILE":
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print("    [+] УСПЕХ: Файл создан/перезаписан.")
            
            elif action == "DELETE_FILE":
                 if os.path.exists(path):
                    os.remove(path)
                    print("    [+] УСПЕХ: Файл удален.")
                 else:
                    print("    [!] ПРЕДУПРЕЖДЕНИЕ: Файл для удаления не найден.")

        except Exception as e:
            print(f"    [!] ОШИБКА ФАЙЛА: {e}")
            return

    # --- 3. Синхронизация с Git (если есть сообщение коммита) ---
    if commit_message:
        print("\n--- [ АВТОМАТИЧЕСКАЯ СИНХРОНИЗАЦИЯ ] ---")
        if not run_git_command("git add ."): return
        if not run_git_command('git commit -m "{commit_message}"', commit_message): return
        if not run_git_command("git push origin main"):
             print("\n[!] ПРЕДУПРЕЖДЕНИЕ: Не удалось отправить на GitHub. Изменения закоммичены локально.")
    else:
        print("\n[i] Сообщение коммита не указано. Автоматическая синхронизация пропущена.")

    print("\n--- [ ЗАВЕРШЕНО ] ---")

if __name__ == "__main__":
    apply_modifications()